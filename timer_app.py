"""Example app that implements a count down timer
See the on_intent handler for required intents
"""

import asyncio
import logging
from dataclasses import dataclass
import time

from rhasspyhermes.nlu import NluIntent

from rhasspyhermes_app import HermesApp, EndSession
from rhasspyhermes.dialogue import DialogueNotification, DialogueStartSession

_LOGGER = logging.getLogger("TimerApp")
_LOGGER.setLevel(logging.DEBUG)


app = HermesApp("TimerApp")
activeTimerBySite = {}


@dataclass
class ActiveTimer(object):
    started_at: float
    handle: asyncio.Handle
    total_seconds: int


def extract_slot_value(intent: NluIntent, slot_name: str, default=None):
    """extracts the value of a slot"""

    slot = next(filter(lambda slot: slot.slot_name == slot_name, intent.slots), None)
    if slot:
        if slot.value["kind"] != "Unknown":
            return slot.value.get("value", default)
    return default


def countdown_reached(site_id):
    """Starts a notification session to notify the user about the countdown"""
    if site_id in activeTimerBySite:
        del activeTimerBySite[site_id]
    notification = DialogueNotification("Die Zeit ist abgelaufen")
    app.publish(DialogueStartSession(init=notification, site_id=site_id))


@app.on_intent("StopTimer")
def stop_timer(intent: NluIntent):
    """This intent stops a running timer for the site"""
    active_timer = activeTimerBySite.get(intent.site_id)
    if active_timer:
        active_timer.handle.cancel()
        del activeTimerBySite[intent.site_id]
        return EndSession(f"Timer gestoppt")  # "timer stopped"
    else:
        return EndSession(f"Es ist kein Timer gesetzt")  # "No timer exists"

@app.on_intent("QueryTimer")
def query_timer(intent: NluIntent):
    """This intent allows to query the remaing time on the countdown timer"""
    active_timer = activeTimerBySite.get(intent.site_id)
    if active_timer:
        remaining_seconds = active_timer.total_seconds - (time.time() - active_timer.started_at)
        return EndSession(f"Es verbleiben {remaining_seconds:.0f} Sekunden")  # "There are _ seconds remaining"
    else:
        return EndSession(f"Es ist kein Timer gesetzt")   # "No timer exists"

@app.on_intent("StartTimer")
def start_timer(intent: NluIntent):
    """
    This intent starts a new countdown timer.
    Two slots are supported:
        minutes: int
        seconds: int
    At least one has to be set
    """
    if intent.site_id in activeTimerBySite:
        return EndSession(f"Es ist bereits ein Timer aktiv")  # "There already is an active timer"
    _LOGGER.debug(intent)
    minutes = extract_slot_value(intent, "minutes", 0)
    seconds = extract_slot_value(intent, "seconds", 0)
    total_seconds = minutes * 60 + seconds
    if total_seconds >= 10:
        text = "Neuer Timer gesetzt für"   # "new timer set for"
        if minutes > 0:
            text = f"{text} {minutes} Minuten"  # "_ minutes"
        if seconds > 0:
            text = f"{text} {seconds} Sekunden" # "_ seconds"
        loop = asyncio.get_event_loop()
        handle = loop.call_later(total_seconds, countdown_reached, intent.site_id)
        activeTimerBySite[intent.site_id] = ActiveTimer(started_at=time.time(), handle=handle, total_seconds=total_seconds)
    else:
        text ="Ein Timer muss mindestens 10 Sekunden lang sein"  # "The minimum duration for a timer is 10 seconds"
    return EndSession(text)


app.run()
