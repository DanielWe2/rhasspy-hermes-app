const { Aki } = require('aki-api');
const readline = require('readline');

const region = process.argv[2];

// I don't know anything about node. Can't get it to work without
require('events').EventEmitter.prototype._maxListeners = 100000;

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout,
  console: false,
  terminal: false
});

const readlineFromStdin = function(){
    var response;
    return new Promise(( resolve , reject) => {
        rl.once('line', (userInput) => {
            response = userInput;
            //rl.off("line");
            resolve(response);
        });
        rl.once('close', () => {
            resolve(response);
        });
    });
};

const aki = new Aki(region);

function win() {
      console.log(JSON.stringify({"guess": aki.answers}));
      process.exit();
}

function writeQuestion() {
    question = JSON.stringify({ question: aki.question, answers: aki.answers, progress: aki.progress});
    console.log(question)
}

(async () => {
  await aki.start();
  while( aki.progress < 80 && aki.currentStep < 78) {
    writeQuestion();
    await readlineFromStdin().then(answer => aki.step(answer));
  }
  aki.win().then( win );

})();