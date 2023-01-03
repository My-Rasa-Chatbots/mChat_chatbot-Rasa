from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.types import DomainDict
from rasa_sdk.events import EventType, AllSlotsReset, FollowupAction

import re
import time
import pymongo

# MongoDB connection


def connectDB(coll_name):
    conn_str = "mongodb+srv://keshab:keshab123@cluster0.bqo0o.mongodb.net/?retryWrites=true&w=majority"
    try:
        client = pymongo.MongoClient(conn_str)
        db_name = "marlabs_chatbot"
        my_db = client[db_name]
        my_coll = my_db[coll_name]
        # print("DB Connected successfully:")
        return my_coll
    except pymongo.errors.ConnectionFailure as e:
        print("Database connection problem: ", str(e))

# query DB and send response


def getResponse(response_name):
    coll_name = "responses"
    my_coll = connectDB(coll_name)
    try:
        res = my_coll.find_one({"response_name": response_name})

        if (res == None):
            print("Result None for response name: ", response_name)
            return []
        response = res["response_payload"]
        # print(my_coll.find({"response_name": response_name}).explain()["executionStats"])
        return response
    except pymongo.errors.OperationFailure as e:
        print("MongoDB Operational Failure: ", e.details)
        return []


#########################################
class ActionUtterGreet(Action):
    def name(self) -> Text:
        return "action_utter_greet"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        resp_name = "utter_greet"
        response = getResponse(resp_name)
        dispatcher.utter_message(json_message=response)
        return []

class ActionUtterAboutMarlabs(Action):
    def name(self) -> Text:
        return "action_utter_about_marlabs"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        resp_name = "utter_about_marlabs"
        response = getResponse(resp_name)
        dispatcher.utter_message(json_message=response)
        return []

class ActionUtterWhatDoYouDo(Action):
    def name(self) -> Text:
        return "action_utter_what_do_you_do"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        resp_name = "utter_what_do_you_do"
        response = getResponse(resp_name)
        dispatcher.utter_message(json_message=response)
        return []

class ActionUtterTalkToAdvisor(Action):
    def name(self) -> Text:
        return "action_utter_talk_to_advisor"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        resp_name = "utter_talk_to_advisor"
        response = getResponse(resp_name)
        dispatcher.utter_message(json_message=response)
        return []

class ActionUtterMarlabsCareer(Action):
    def name(self) -> Text:
        return "action_utter_marlabs_career"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        resp_name = "utter_marlabs_career"
        response = getResponse(resp_name)
        dispatcher.utter_message(json_message=response)
        return []

class ActionUtterLatestPublications(Action):
    def name(self) -> Text:
        return "action_utter_latest_publications"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        resp_name = "utter_latest_publications"
        response = getResponse(resp_name)
        dispatcher.utter_message(json_message=response)
        return []