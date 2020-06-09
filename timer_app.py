"""Example app to react to an intent to tell you the time."""
import asyncio
import logging
from asyncio import Handle
from dataclasses import dataclass
import time
import humanize

from rhasspyhermes.nlu import NluIntent

from rhasspyhermes_app import HermesApp
from rhasspyhermes.dialogue import DialogueNotification, DialogueStartSession

_LOGGER = logging.getLogger("TimerApp")
_LOGGER.setLevel(logging.DEBUG)

app = HermesApp("TimerApp")
activeTimerBySite = {}


@dataclass
class ActiveTimer(object):
    started_at: float
    handle: Handle
    total_seconds: int


def extract_slot_value(intent: NluIntent, slot_name: str, default=None):
    slot = next(filter(lambda slot: slot.slot_name == slot_name, intent.slots), None)
    if slot:
        if slot.value["kind"] != "Unknown":
            return slot.value.get("value", default)
    return default


def timeout(site_id, minutes, seconds):
    if site_id in activeTimerBySite:
        del activeTimerBySite[site_id]
    notification = DialogueNotification("Die Zeit ist abgelaufen")
    app.publish(DialogueStartSession(init=notification, site_id=site_id))


@app.on_intent("StopTimer")
def stop_timer(intent: NluIntent):
    active_timer = activeTimerBySite.get(intent.site_id)
    if active_timer:
        active_timer.handle.cancel()
        del activeTimerBySite[intent.site_id]
        return app.EndSession(f"Timer gestoppt")
    else:
        return app.EndSession(f"Es ist kein Timer gesetzt")

@app.on_intent("QueryTimer")
def query_timer(intent: NluIntent):
    active_timer = activeTimerBySite.get(intent.site_id)
    if active_timer:
        remaining_seconds = active_timer.total_seconds - (time.time() - active_timer.started_at)
        return app.EndSession(f"Es verbleiben {remaining_seconds:.0f} Sekunden")
    else:
        return app.EndSession(f"Es ist kein Timer gesetzt")

@app.on_intent("StartTimer")
def start_timer(intent: NluIntent):
    if intent.site_id in activeTimerBySite:
        return app.EndSession(f"Es ist bereits ein Timer aktiv")
    _LOGGER.debug(intent)
    minutes = extract_slot_value(intent, "minutes", 0)
    seconds = extract_slot_value(intent, "seconds", 0)
    total_seconds = minutes * 60 + seconds
    if total_seconds >= 10:
        text = "Timer gesetzt für"
        if minutes > 0:
            text = f"{text} {minutes} Minuten"
        if seconds > 10:
            text = f"{text} {seconds} Sekunden"
        loop = asyncio.get_event_loop()
        handle = loop.call_later(total_seconds, timeout, intent.site_id, minutes, seconds)
        activeTimerBySite[intent.site_id] = ActiveTimer(started_at=time.time(), handle=handle, total_seconds=total_seconds)
    else:
        text ="Ein Timer muss mindestens 10 Sekunden lang sein"
    return app.EndSession(text)


app.run()
