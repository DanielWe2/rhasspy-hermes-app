import subprocess
import sys
import json
import logging

_LOGGER = logging.getLogger("AkinatorSession")
_LOGGER.setLevel(logging.DEBUG)

class Answer(object):
    YES = 0
    NO = 1
    DONT_KNOW = 2
    PROBABLY = 3
    PROBABLY_NOT = 4


class AkinatorSession(object):

    def __init__(self, region):
        self.region = region
        self.proc = None

    def start_game(self):
        self.proc = subprocess.Popen(['node', 'akinatorNodeWrapper/akinator.js', self.region],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                stdin=subprocess.PIPE,
                                     encoding='utf8',
                                     bufsize=0
                                     )

    def next(self):
        line = self.proc.stdout.readline()
        _LOGGER.debug("got line: %s", line)
        jsonResponse = json.loads(line)

        if "guess" in jsonResponse:
            return True, jsonResponse.get("guess")[0].get("name")
        else:
            return False, jsonResponse.get("question")

    def answer(self, answer ):
        self.proc.stdin.write(str(answer)+"\n")

    def stop(self):
        self.proc.kill()
