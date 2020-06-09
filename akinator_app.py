from datetime import datetime
import logging

from rhasspyhermes_app import HermesApp, TopicData
from rhasspyhermes.dialogue import DialogueContinueSession, DialogueEndSession

from akinatorNodeWrapper import AkinatorSession, Answer
import codecs
import json

_LOGGER = logging.getLogger("AkinatorApp")
_LOGGER.setLevel(logging.DEBUG)

app = HermesApp("AkinatorApp")

akinator_sessions = {}

region = "de"

intent_filter = ["AnswerYes", "AnswerNo", "AnswerDontKnow", "AnswerProbably", "AnswerProbablyNot", "AnswerStop"]


def handle_answer(answer, session_id):
    akinator = akinator_sessions.get(session_id)
    if not akinator:
        return app.EndSession(text="Es läuft noch kein Spiel. Sage Starte Akinator um ein neues spiel zu starten")
    try:
        akinator.answer(answer)
        finished, text = akinator.next()
        if not finished:
            return app.ContinueSession(text=text, intent_filter=intent_filter, send_intent_not_recognized=True)
        else:
            return app.EndSession(text="Du hast an folgende Person gedacht: " + text)
    except Exception as e:
        _LOGGER.exception(e)
        del akinator_sessions[session_id]
        app.EndSession(text="Es gab einen Fehler. Das spiel wird beendet")
        akinator.stop()


@app.on_intent("AnswerYes")
def handle_yes(intent):
    return handle_answer(Answer.YES, intent.session_id)

@app.on_intent("AnswerNo")
def handle_yes(intent):
    return handle_answer(Answer.NO, intent.session_id)

@app.on_intent("AnswerDontKnow")
def handle_dont_know(intent):
    return handle_answer(Answer.DONT_KNOW, intent.session_id)

@app.on_intent("AnswerProbably")
def handle_probably(intent):
    return handle_answer(Answer.PROBABLY, intent.session_id)

@app.on_intent("AnswerProbablyNot")
def handle_probably_not(intent):
    return handle_answer(Answer.PROBABLY_NOT, intent.session_id)

@app.on_intent("AnswerStop")
def handle_stop(intent):
    akinator = akinator_sessions.get(intent.session_id)
    if not akinator:
        return app.EndSession(text="Es läuft noch kein Spiel. Sage Starte Akinator um ein neues spiel zu starten")
    akinator_sessions[intent.session_id].stop()
    del akinator_sessions[intent.session_id]
    return app.EndSession(text="Vielen Dank fürs spielen")


@app.on_intent("StartAkinator")
def start_akinator(intent):
    akinator = AkinatorSession(region)
    akinator_sessions[intent.session_id] = akinator
    akinator.start_game()
    _, question = akinator.next()
    intro = "Bitte denke an eine Person. ich werde sie erraten. Die erste Frage lautet: "
    return app.ContinueSession(text=intro+question, intent_filter=intent_filter, send_intent_not_recognized=True )

@app.on_topic("hermes/dialogueManager/intentNotRecognized")
def intent_not_recognized(data: TopicData, payload: bytes):
    _LOGGER.debug("not recognized: " + str(data) + str(payload))

    payload_json = json.loads(payload.decode("utf-8"))
    session_id = payload_json.get("sessionId")
    site_id = payload_json.get("siteId")
    if session_id in akinator_sessions:
        text = 'Das habe ich nicht verstanden'
        app.publish(
            DialogueContinueSession(
                session_id=session_id,
                site_id=site_id,
                text=text,
                intent_filter=intent_filter,
                custom_data=None,
                send_intent_not_recognized=True,
                slot=None
                )
        )

app.run()
