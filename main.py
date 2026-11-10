import urllib.parse

import splunklib.client as client
import splunklib.results as results
import subprocess
import os
from pathlib import Path
from dotenv import load_dotenv
import requests
import json
from flask import Flask
from slackeventsapi import SlackEventAdapter
from datetime import timedelta, datetime
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from requests.compat import urljoin

processed_message_ids = set()

def connect_to_splunk(username,password,host='splunk-eu-api.adobelaas.com',port='443',owner='admin',app='search',sharing='user'):
    try:
        service = client.connect(host=host, port=port,username=username, password=password,owner=owner,app=app,sharing=sharing)
        if service:
            print("Splunk service created successfully")
            print("------------------------------------")
        return service
    except Exception as e:
        print(e)

def parse_request_ids(sentence):
    print("Given sentence is: ")
    print(sentence)
    list_words = sentence.split()
    request_ids = []
    print("After splitting, the array becomes:")
    print(list_words)
    for word in list_words:
        formatted_word = word.replace('"', '').replace(".", "").replace("<", "").replace(">", '').replace('`', '')
        if len(formatted_word) > 15:
            request_ids.append(formatted_word)
    return request_ids

def get_request_ids(text):
    data = {
        "messages": [ { "role": "system", "content": "You are requestId provider" }, { "role": "user", "content": "What is the requestId in this message and output only the requestIds and nothing else" + text }],
        "temperature": "0.7",
        "max_tokens": "-1",
        "stream": "false"
    }

    json_data = json.dumps(data)
    curl_command = [
        'curl',
        'http://localhost:1234/v1/chat/completions',
        '-H', 'Content-Type: application/json',
        '-d', json_data

    ]

    # Execute the curl command
    try:
        response = subprocess.run(curl_command, capture_output=True, text=True, check=True)
        json_string = response.stdout
        json_object = json.loads(json_string)
        llm_response_for_requestId = str(json_object['choices'][0]['message']['content'])
        request_ids = parse_request_ids(llm_response_for_requestId)
        return request_ids[0]
    except subprocess.CalledProcessError as e:
        # If an error occurs, you can catch it here
        print(f"Error executing the command: {e}")

def get_failure_analysis(logs):
    data = {
        "messages": [ { "role": "system", "content": "You are analysing failure from the provided logs and please respone in 2 3 sentences" }, { "role": "user", "content": "what is the failure reason in the given logs" + logs }],
        "temperature": "0.7",
        "max_tokens": "-1",
        "stream": "false"
    }

    json_data = json.dumps(data)
    curl_command = [
        'curl',
        'http://localhost:1234/v1/chat/completions',
        '-H', 'Content-Type: application/json',
        '-d', json_data
    ]

    # Execute the curl command
    try:
        response = subprocess.run(curl_command, capture_output=True, text=True, check=True)
        print(f"**********Log analysis**********")
        json_string = response.stdout
        json_object = json.loads(json_string)
        return str(json_object['choices'][0]['message']['content'])
    except subprocess.CalledProcessError as e:
        # If an error occurs, you can catch it here
        print(f"Error executing the command: {e}")

def run_normal_mode_search(splunk_service,search_string,payload={},splunk_link_data={}):
    try:
        job = splunk_service.jobs.create(search_string,**payload)
        #print(job.content)
        splunk_host = 'splunk-eu.corp.adobe.com'
        splunk_link = f"http://{splunk_host}/app/search/search?q={urllib.parse.quote(search_string)}&latest={payload['latest_time']}&earliest={payload['earliest_time']}&sid={job.sid}"
        #print(splunk_link)
        splunk_link_data['link'] = splunk_link
        #print(job.preview)
        while True:
            while not job.is_ready():
                pass
            if job["isDone"] == "1":
                print("...done!\n")
                break
        # Get properties of the job
        print ("The number of events: ", job["eventCount"])
        print ("The number of results:", job["resultCount"])
        print ("Search duration:      ", job["runDuration"], "seconds")
        print ("This job expires in:  ", job["ttl"], "seconds")
        # result_stream = job.results(output_mode='json')
        # print(result_stream)
        print(job.links)

        rr = results.JSONResultsReader(job.preview(output_mode='json'))
        print(rr)
        log_messages = ""
        for result in rr:
            if isinstance(result, results.Message):
                print ('%s: %s' % (result.type, result.message))
            elif isinstance(result, dict):
                log_messages += result['message']
                log_messages += "\n"
                #print (result)
        if rr.is_preview:
            print("Preview of a running search job.")
        else:
            print("Job is finished. Results are final.")
        return log_messages
    except Exception as e:
        print("printing exception 1")
        print(e)

def main(text, logs_snippet):
    try:
        #request_id = "itTest-4d931398-946b-4423-ab59-1256d65178d9"
        request_id = get_request_ids(text)
        splunk_service = connect_to_splunk(username='api_acp_cs_cmm',password='Splunk123')
        search_string = "search index=acp-cs-stage-irl1-cmm %s sourcetype=*copyRes* level=ERROR | table logger_name, message" % request_id
        print(search_string)
        earliest_time = (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%dT%H:%M:%S')
        latest_time = (datetime.now()).strftime('%Y-%m-%dT%H:%M:%S')
        payload = {"exec_mode": "blocking", 'earliest_time': earliest_time,
                   'latest_time': latest_time}

        splunk_link_data = {}
        log_messages = run_normal_mode_search(splunk_service,search_string, payload, splunk_link_data)
        print(splunk_link_data['link'])
        print(log_messages)
        splunk_link_str = splunk_link_data['link']
        llm_analysis = get_failure_analysis(log_messages)

        #output = f"Executive Summary of the response. <{splunk_link_str}|Splunk link> for reference" #get_failure_analysis(log_messages)
        output = f"{llm_analysis}\n<{splunk_link_str}|Splunk link> for reference"
        print(output)
        logs_snippet['logs'] = log_messages
        return output
    except Exception as e:
        print("printing exception 2")
        print(e)

env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
slack_event_adapter = SlackEventAdapter(os.environ['SIGNING_SECRET'], '/slack/events', app)

BOT_ID = "U067CUZFTDL"

def post_message_to_slack(channel, text, tps, snippet_content):

    #snippet_content = "This is a text snippet that will be uploaded to Slack."
    # Save the snippet content to a temporary file
    snippet_file_path = "logs.txt"
    with open(snippet_file_path, "w") as file:
        file.write(snippet_content)
    # Upload the snippet to Slack
    client = WebClient(token=os.environ['SLACK_TOKEN'])
    try:
        response = client.files_upload(
            channels=channel,
            file=snippet_file_path,
            initial_comment=text,
            thread_ts=tps
        )
        print("Message with snippet sent to Slack successfully" + str(response.data))
        return response.data
    except SlackApiError as e:
        print(f"Error sending message to Slack: {e.response['error']}")
    #
    # payload = {
    #     'token': os.environ['SLACK_TOKEN'],
    #     'channel': channel,
    #     'text': text,
    #     'thread_ts': tps,
    # }
    # final_response = requests.post('https://slack.com/api/chat.postMessage', data=payload).json()
    # print(final_response)
    #return final_response

@slack_event_adapter.on("message")
def message(payload):
    event = payload.get('event', {})
    channel_id = event.get('channel')
    message_id = event.get('message_id')
    if message_id not in processed_message_ids:
        processed_message_ids.add(message_id)
        user_id = event.get('user')
        text = event.get('text')
        tpss = event.get('ts')
        print(text)
        logs_snippet = {}
        slack_response = main(text, logs_snippet)
        if BOT_ID != user_id:
            post_message_to_slack(channel=channel_id, text=slack_response, tps=tpss, snippet_content=logs_snippet['logs'])

if __name__ == "__main__":
    app.run(debug=True, port=8000)
