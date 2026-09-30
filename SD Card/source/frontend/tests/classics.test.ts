import test from "node:test";
import assert from "node:assert/strict";
import {SnakeGame,BreakerGame,RallyGame,brickLayout,BRICK_LAYOUTS,smoothPaddle,PONG_BALL_TEMPO,PONG_TEMPO,PONG_MAX_SPEED} from "../src/classics.ts";
test("Snake runs more slowly, with bounded variable reaction timing and interpolated motion",()=>{
  let seed=57;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const game=new SnakeGame(random),first=game.head;game.advance(.1);assert.equal(game.head,first);
  game.advance(.06);assert.notEqual(game.head,first);assert.ok(game.moveDelay>=.125 && game.moveDelay<=.24);
  game.advance(game.moveDelay/2);const displayed=game.visualBody()[0],from=game.route[first],to=game.route[game.head];
  assert.deepEqual(displayed,[(from[0]+to[0])/2,(from[1]+to[1])/2]);
  const delays=new Set<number>();for(let i=0;i<200;i++){game.advance(.25);delays.add(game.moveDelay);assert.ok(game.moveDelay>=.125 && game.moveDelay<=.24);}
  assert.ok(delays.size>10);
});
test("an occasional missed Snake turn produces a real wall loss, not a fabricated score reset",()=>{
  const game=new SnakeGame(()=>0);game.body=[31,30,29,28,27,26,25,24];game.head=31;game.moves=20;game.food=40;game.score=50;
  game.step();assert.equal(game.pause,20);assert.equal(game.head,31);assert.equal(game.score,50);
});
test("paddles accelerate, brake and reverse without instantaneous velocity jumps",()=>{
  let position=350,velocity=0;const dt=1/240;
  for(let i=0;i<500;i++){
    const previous=velocity,target=i<250?640:60;
    [position,velocity]=smoothPaddle(position,velocity,target,dt,340,52,648);
    assert.ok(Math.abs(velocity-previous)<=1200*dt+1e-8);assert.ok(Math.abs(velocity)<=340);assert.ok(position>=52 && position<=648);
  }
  const [,reversed]=smoothPaddle(350,200,60,dt,340,52,648);assert.ok(reversed>0 && reversed<200);
});
test("breaker paddle continuously follows the ball both rising and high in the field",()=>{
  for(const [y,vy] of [[330,-205],[90,205]]){
    const game=new BreakerGame(()=>.2);game.bricks.fill(false);game.bricks[0]=true;
    game.x=350;game.y=y;game.vy=vy;game.paddle=game.paddleAim=150;game.paddleVelocity=0;
    for(let i=0;i<24;i++)game.step(1/240);
    assert.ok(game.paddle>150);assert.ok(game.paddleVelocity>0);
    assert.ok(game.paddle<game.x,"tracking has natural lag rather than snapping beneath the ball");
  }
});
test("breaker paddle brakes and reverses smoothly when the ball changes direction",()=>{
  const game=new BreakerGame(()=>.2);game.bricks.fill(false);game.bricks[0]=true;
  game.x=350;game.y=330;game.vx=-155;game.vy=-205;game.paddle=game.paddleAim=350;game.paddleVelocity=155;
  for(let i=0;i<120;i++){
    const previous=game.paddleVelocity;game.step(1/240);
    assert.ok(Math.abs(game.paddleVelocity-previous)<=1800/240+1e-8);
    if(i===0)assert.ok(game.paddleVelocity>0,"momentum persists briefly after the ball reverses");
  }
  assert.ok(game.paddle<350);assert.ok(game.paddleVelocity<0);
});
test("breaker paddle smoothly tracks and returns a ball descending out of the bricks",()=>{
  const game=new BreakerGame(()=>.2);game.bricks.fill(false);game.bricks[0]=true;
  game.x=350;game.y=275;game.vx=155;game.vy=205;game.paddle=game.paddleAim=350;game.paddleVelocity=0;
  let returned=false;
  for(let i=0;i<190;i++){game.step(1/240);if(game.vy<0){returned=true;break;}}
  assert.ok(game.paddle>400);assert.ok(returned);assert.equal(game.lost,false);
});
test("breaker uses its lower speed ceiling, quicker bounded acceleration and filtered aim",()=>{
  const game=new BreakerGame(()=>.2);game.bricks.fill(false);game.bricks[0]=true;
  game.x=620;game.y=330;game.vx=0;game.vy=-205;game.paddle=game.paddleAim=80;game.paddleVelocity=0;
  game.step(1/240);assert.ok(game.paddleAim>80 && game.paddleAim<150,"aim eases toward the new target");
  let peak=0;
  for(let i=0;i<180;i++){
    const previous=game.paddleVelocity;game.step(1/240);peak=Math.max(peak,game.paddleVelocity);
    assert.ok(Math.abs(game.paddleVelocity)<=280+1e-8);
    assert.ok(Math.abs(game.paddleVelocity-previous)<=1800/240+1e-8);
  }
  assert.ok(peak>270);
});
test("breaker eases to rest after a miss rather than freezing its paddle",()=>{
  const game=new BreakerGame(()=>.2);game.paddle=350;game.paddleVelocity=240;game.clearedPause=1.2;game.lost=true;
  game.step(1/240);assert.ok(game.paddle>350);assert.ok(game.paddleVelocity>=232.5 && game.paddleVelocity<240);
  game.step(.5);assert.ok(game.paddleVelocity<1);assert.equal(game.lost,true);
});
test("twenty distinct brick layouts share the same workload, row density and symmetry",()=>{
  const layouts=BRICK_LAYOUTS.map((_,i)=>brickLayout(i));
  assert.equal(layouts.length,20);assert.equal(new Set(layouts.map(board=>JSON.stringify(board))).size,20);
  layouts.forEach(board=>{
    assert.equal(board.length,80);assert.equal(board.filter(Boolean).length,32);
    for(let y=0;y<8;y++){
      assert.equal(board.slice(y*10,y*10+10).filter(Boolean).length,4);
      for(let x=0;x<5;x++)assert.equal(board[y*10+x],board[y*10+9-x]);
    }
  });
});
test("all twenty levels retain speed and score until the capped run ends as a loss",()=>{
  const game=new BreakerGame(()=>.87),seen=new Set<number>(),speed=Math.hypot(game.vx,game.vy);
  for(let level=1;level<=20;level++){
    assert.equal(game.level,level);seen.add(game.layout);assert.equal(game.bricks.filter(Boolean).length,32);
    game.score+=320;game.best=game.score;game.bricks.fill(false);game.pendingLevel=true;game.x=350;game.y=330;
    game.step(.01);assert.equal(game.score,level*320);assert.equal(Math.hypot(game.vx,game.vy),speed);
    assert.equal(game.lost,level===20);
  }
  assert.equal(seen.size,20);assert.equal(game.level,20);assert.equal(game.misses,1);
  game.step(1.3);assert.equal(game.level,1);assert.equal(game.score,0);assert.equal(game.best,6400);assert.equal(game.lost,false);
  assert.equal(game.bricks.filter(Boolean).length,32);assert.equal(Math.hypot(game.vx,game.vy),speed);
});
test("cleared walls advance without resetting score or respawning the ball",()=>{
  const game=new BreakerGame(()=>.2),layout=game.layout;game.score=240;game.bricks.fill(false);game.pendingLevel=true;game.x=210;game.y=330;game.vx=155;
  game.step(.01);assert.equal(game.level,2);assert.equal(game.score,240);assert.notEqual(game.layout,layout);assert.ok(Math.abs(game.x-211.55)<.001);assert.ok(game.y<330);assert.equal(game.clearedPause,0);
});
test("brick-breaker resets a run only after a lost ball, retaining best score",()=>{
  const game=new BreakerGame(()=>.2);game.score=game.best=230;game.level=4;game.y=469;game.vy=205;
  game.step(.01);assert.equal(game.lost,true);assert.equal(game.score,230);
  game.step(1.3);assert.equal(game.score,0);assert.equal(game.best,230);assert.equal(game.level,1);assert.equal(game.lost,false);assert.ok(game.bricks.some(Boolean));
});
test("Snake keeps score after filling the board but resets after losing",()=>{
  const game=new SnakeGame(()=>0);game.body=Array.from({length:640},(_,i)=>i);game.head=0;game.food=-1;game.score=6320;
  game.step();assert.equal(game.won,true);for(let i=0;i<20;i++)game.step();assert.equal(game.score,6320);
  game.won=false;game.pause=1;game.step();assert.equal(game.score,0);
});
test("Pong keeps point scores until a match is lost (eleven, win by two)",()=>{
  const game=new RallyGame();game.score=[10,9];game.x=709;game.vx=240;game.step(.01);assert.deepEqual(game.score,[11,9]);assert.equal(game.matchOver,true);game.step(3.1);assert.deepEqual(game.score,[0,0]);
});
test("Snake route is a continuous closed grid path without duplicate cells",()=>{
  const game=new SnakeGame();assert.equal(game.route.length,640);assert.equal(new Set(game.route.map(p=>p.join(","))).size,640);
  game.route.forEach(([x,y],i)=>{const [nx,ny]=game.route[(i+1)%640];assert.equal(Math.abs(x-nx)+Math.abs(y-ny),1);});
});
test("Snake eats, grows, and never intersects itself or places food on its body",()=>{
  const game=new SnakeGame(()=>0);let grew=false;
  for(let i=0;i<3000;i++){game.step();grew ||=game.body.length>8;assert.equal(new Set(game.body).size,game.body.length);assert.ok(!game.body.includes(game.food));}
  assert.ok(grew);
});
test("Snake actively takes the short route to an apple and scores",()=>{
  const game=new SnakeGame();game.food=game.route.findIndex(([x,y])=>x===7 && y===2);
  game.step();game.step();assert.equal(game.score,10);assert.equal(game.body.length,9);assert.deepEqual(game.route[game.head],[7,2]);
});
test("brick breaker hits bricks, scores, remains in bounds and keeps elastic speed",()=>{
  const game=new BreakerGame(),speed=Math.hypot(game.vx,game.vy);let hit=false;
  for(let i=0;i<3000;i++){game.step(.032);hit ||=game.bricks.some(b=>!b);assert.ok(game.x>=8 && game.x<=692);assert.ok(game.y>=8 && game.y<=470);assert.ok(Math.abs(Math.hypot(game.vx,game.vy)-speed)<1e-9);}
  assert.ok(hit);assert.ok(game.best>0);
});
test("Pong bots return real collisions and award points after a missed ball",()=>{
  const game=new RallyGame();for(let i=0;i<3000;i++)game.step(.032);assert.ok(game.rallies>0);
  const before=game.score[0];game.x=709;game.y=20;game.vx=240;game.pause=0;game.step(.032);
  assert.equal(game.score[0],before+1);assert.equal(game.x,350);assert.ok(game.pause>0);
});
test("Pong only tracks with the receiving paddle and leaves the other off-center",()=>{
  for(const direction of [-1,1]){
    const game=new RallyGame(()=>.5);game.vx=direction*240;game.left=100;game.right=360;game.reactionDelay=0;
    game.step(.1);
    if(direction<0){assert.notEqual(game.left,100);assert.equal(game.right,360);}
    else {assert.equal(game.left,100);assert.notEqual(game.right,360);}
  }
});
test("Pong hands over after smooth follow-through without moving both paddles at once",()=>{
  const game=new RallyGame(()=>.5);game.vx=240;game.vy=125;game.y=230;game.reactionDelay=0;game.leftVelocity=200;game.left=100;game.right=360;
  for(let i=0;i<Math.ceil(200/(1200*PONG_TEMPO**2/240));i++){
    const before=game.leftVelocity,right=game.right;game.step(1/240);
    assert.equal(game.right,right);assert.ok(Math.abs(game.leftVelocity-before)<=5+1e-8);
  }
  assert.equal(game.leftVelocity,0);const left=game.left;game.step(.1);
  assert.equal(game.left,left);assert.notEqual(game.right,360);
  for(let i=0;i<4000;i++){
    const [left,right]=[game.left,game.right];game.step(1/240);
    assert.ok(game.left===left || game.right===right,"only one paddle moves during a simulation step");
  }
  assert.ok(game.rallies>0);
});
const pongRandom=(seed:number)=>()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
test("Pong serves vary by run and shot choices stay stable between collisions",()=>{
  const serves=Array.from({length:20},(_,i)=>new RallyGame(pongRandom(i+1)));
  serves.forEach(game=>assert.ok(Math.hypot(game.vx,game.vy)>=220*PONG_TEMPO*PONG_BALL_TEMPO && Math.hypot(game.vx,game.vy)<=240*PONG_TEMPO*PONG_BALL_TEMPO));
  assert.equal(new Set(serves.map(g=>`${g.y},${g.vx},${g.vy}`)).size,20);
  let calls=0;const game=new RallyGame(()=>{calls++;return .5;});
  const before=calls,offset=game.shotOffset;game.step(.1);
  assert.equal(calls,before);assert.equal(game.shotOffset,offset);
});
test("Pong's ball-only pace rises 12% without changing paddle tempo",()=>{
  const game=new RallyGame(()=>.5);
  assert.ok(Math.abs(Math.hypot(game.vx,game.vy)-230*PONG_TEMPO*PONG_BALL_TEMPO)<1e-9);
  assert.equal(game.receiverSpeed,255*PONG_TEMPO);
  assert.equal(PONG_MAX_SPEED,380*PONG_TEMPO*PONG_BALL_TEMPO);
});
test("Pong paddle contacts cannot retrace the incoming path",()=>{
  const game=new RallyGame(()=>.5);game.x=644;game.y=215.2;game.vx=200;game.vy=62;
  game.right=230;game.rightVelocity=0;game.reactionDelay=.2;game.shotOffset=0;
  const retrace=-Math.atan2(game.vy,Math.abs(game.vx));
  game.step(.01);
  assert.ok(game.vx<0 && game.rallies===1);
  assert.ok(Math.abs(Math.atan2(game.vy,Math.abs(game.vx))-retrace)>=.199);
});
test("Pong produces varied legal rallies and real points during sustained seeded play",()=>{
  for(const seed of [7,83,191]){
    const game=new RallyGame(pongRandom(seed)),angles=new Set<number>();let hits=0,points=0;
    // Observe the same amount of play after the shared tempo slowdown.
    for(let i=0;i<Math.ceil(36000/PONG_TEMPO);i++){
      const before=game.rallies,score=game.score[0]+game.score[1],left=game.left,right=game.right;
      game.step(1/240);
      assert.ok(game.left===left || game.right===right);
      assert.ok(game.left>=52 && game.left<=408 && game.right>=52 && game.right<=408);
      assert.ok(Math.hypot(game.vx,game.vy)<=PONG_MAX_SPEED+.001);
      assert.ok(Math.abs(game.vx)>80,"no nearly vertical stalled rally");
      assert.ok(Math.abs(game.leftVelocity)<=280*PONG_TEMPO+.001 && Math.abs(game.rightVelocity)<=280*PONG_TEMPO+.001);
      if(game.rallies>before){hits++;angles.add(Math.round(Math.atan2(game.vy,Math.abs(game.vx))*100));}
      if(game.score[0]+game.score[1]>score)points++;
    }
    assert.ok(hits>=10,`seed ${seed}: enough actual paddle returns`);
    assert.ok(angles.size>=8,`seed ${seed}: varied shot angles`);
    assert.ok(points>=2,`seed ${seed}: rallies end through genuine misses`);
  }
});
