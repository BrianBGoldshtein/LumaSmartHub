export const INVADER_COLUMNS=11;
export const INVADER_ROWS=5;
export const INVADER_COUNT=INVADER_COLUMNS*INVADER_ROWS;
export const INVADER_PLAYER_SPEED=120;
export type InvaderShot={x:number;y:number;enemy:boolean};

const ALIEN_STEP=48;
const ALIEN_ROW_STEP=28;
const ALIEN_SIZE=24;
const ALIEN_LEFT_MIN=8;
const ALIEN_LEFT_MAX=136;
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n));

/** A small autonomous, persistent Space Invaders match for Luma's interludes. */
export class SpaceInvadersGame {
  alive:boolean[]=Array.from({length:INVADER_COUNT},()=>true);
  shots:InvaderShot[]=[];
  playerX=320;playerVelocity=INVADER_PLAYER_SPEED;aimX=320;turnCooldown=.55;
  fleetX=40;fleetY=42;direction:1|-1=1;
  score=0;best=0;wave=1;lives=3;
  phase:"play"|"wave"|"redeploy"|"lost"="play";pause=0;shield=0;
  shootTimer=.3;enemyTimer=.85;thinkTimer=.15;
  rng:number;

  constructor(seed=Math.floor(Math.random()*0xffffffff)){
    this.rng=(seed>>>0)||0x9e3779b9;
  }

  private random(){
    let x=this.rng;x^=x<<13;x^=x>>>17;x^=x<<5;this.rng=x>>>0;
    return this.rng/0x100000000;
  }

  private livingCount(){return this.alive.reduce((count,isAlive)=>count+Number(isAlive),0);}

  private alien(index:number){
    const row=Math.floor(index/INVADER_COLUMNS),column=index%INVADER_COLUMNS;
    return {row,column,x:this.fleetX+column*ALIEN_STEP,y:this.fleetY+row*ALIEN_ROW_STEP};
  }

  private lowestShooters(){
    const result:number[]=[];
    for(let column=0;column<INVADER_COLUMNS;column++){
      for(let row=INVADER_ROWS-1;row>=0;row--){
        const index=row*INVADER_COLUMNS+column;
        if(this.alive[index]){result.push(index);break;}
      }
    }
    return result;
  }

  private think(){
    this.thinkTimer=.19+this.random()*.34;
    const threat=this.shots.filter(shot=>shot.enemy&&shot.y>235&&Math.abs(shot.x-this.playerX)<115)
      .sort((a,b)=>b.y-a.y)[0];
    if(threat){
      // React to one dangerous lane, with a little hesitation and imperfect aim.
      const escape=threat.x>=this.playerX?this.playerX-105:this.playerX+105;
      this.aimX=clamp(escape+(this.random()-.5)*54,30,610);
      return;
    }
    // Stay committed to one shot long enough for it to reach the formation.
    if(this.shots.some(shot=>!shot.enemy))return;
    const columns=this.lowestShooters();
    if(!columns.length)return;
    const target=this.alien(columns[Math.floor(this.random()*columns.length)]);
    if(this.random()>.12)this.aimX=clamp(target.x+ALIEN_SIZE/2+(this.random()-.5)*62,30,610);
  }

  private chooseDirection(){
    const current=this.playerVelocity<0?-1:1,delta=this.aimX-this.playerX;
    let direction:1|-1=Math.abs(delta)>46?(delta<0?-1:1):this.random()<.24?(current===1?-1:1):current;
    const interval=.48+this.random()*.44;
    const room=direction===1?618-this.playerX:this.playerX-22;
    // Leave enough runway to finish the whole cooldown at constant speed.
    // If the selected heading points too close to a wall, glide back inward.
    if(room<INVADER_PLAYER_SPEED*interval+12)direction=direction===1?-1:1;
    this.playerVelocity=direction*INVADER_PLAYER_SPEED;
    this.turnCooldown=interval;
  }

  private predictedShipX(direction:1|-1,seconds:number){
    const span=618-22,period=2*span;
    const distance=this.playerX-22+direction*INVADER_PLAYER_SPEED*seconds;
    const reflected=((distance%period)+period)%period;
    return 22+(reflected<=span?reflected:period-reflected);
  }

  private evadeIncoming(){
    const bulletSpeed=176+this.wave*5;
    const threats=this.shots.filter(shot=>shot.enemy&&shot.y<384)
      .map(shot=>({shot,first:Math.max(0,(350-shot.y)/bulletSpeed),last:(384-shot.y)/bulletSpeed}))
      .filter(item=>item.last>=0&&item.first<=1.9);
    if(!threats.length)return;

    // Judge each heading over the whole time a shot crosses the ship's height,
    // not just at y=350. That catches a turn whose path clips the bullet a few
    // frames before/after the nominal impact point.
    const clearances=(direction:1|-1)=>threats.map(({shot,first,last})=>{
      let closest=Infinity;
      for(let time=first;time<=Math.min(last,1.9)+.0125;time+=.025){
        closest=Math.min(closest,Math.abs(this.predictedShipX(direction,time)-shot.x));
      }
      closest=Math.min(closest,Math.abs(this.predictedShipX(direction,Math.min(last,1.9))-shot.x));
      return closest;
    });
    const risk=(distances:number[])=>distances.reduce((sum,distance)=>sum+Math.max(0,56-distance)**2,0);
    const current:1|-1=this.playerVelocity<0?-1:1,other:1|-1=current===1?-1:1;
    const currentDistances=clearances(current),otherDistances=clearances(other);
    const currentCollisions=currentDistances.filter(distance=>distance<=20).length;
    const otherCollisions=otherDistances.filter(distance=>distance<=20).length;
    const currentRisk=risk(currentDistances),otherRisk=risk(otherDistances);

    // Stay committed when the current glide is safe. If it isn't, only reverse
    // when the whole alternative route is materially safer: don't dodge one
    // shot by turning directly into another. Collision count takes priority;
    // otherwise use a little hysteresis to prevent nervous direction-flipping.
    if(Math.min(...currentDistances)>=56)return;
    const safer=otherCollisions<currentCollisions||
      (otherCollisions===currentCollisions&&otherRisk+64<currentRisk);
    if(!safer)return;

    this.playerVelocity=other*INVADER_PLAYER_SPEED;
    this.aimX=clamp(this.playerX+other*150,30,610);
    // Urgent avoidance may bypass ordinary turn timing, then holds a clean glide.
    this.turnCooldown=Math.max(this.turnCooldown,.48);
  }

  private startWave(){
    this.alive=Array.from({length:INVADER_COUNT},()=>true);
    this.shots=[];this.fleetX=40;this.fleetY=42;this.direction=1;
    this.aimX=this.playerX;this.chooseDirection();
    this.shootTimer=.25+this.random()*.25;
    this.enemyTimer=.65+this.random()*.5;
    this.thinkTimer=.1+this.random()*.25;
    this.shield=.6;this.phase="play";this.pause=0;
  }

  private redeploy(){
    if(this.phase!=="play")return;
    // An advancing formation can force a tactical reset, but it is not a lost
    // life: keep every survivor, the score, wave and remaining lives intact.
    this.phase="redeploy";this.pause=.9;this.shots=[];
  }

  private finishRedeploy(){
    this.fleetX=32+this.random()*32;this.fleetY=42;this.direction=this.random()<.5?-1:1;
    this.playerX=320;this.aimX=320;this.shots=[];this.shield=1;
    this.chooseDirection();this.phase="play";this.pause=0;
  }

  private lose(){
    if(this.phase!=="play"||this.lives>0)return;
    this.phase="lost";this.pause=1.35;this.shots=[];this.lives=0;
  }

  private resetRun(){
    this.score=0;this.wave=1;this.lives=3;this.playerX=320;
    this.playerVelocity=this.random()<.5?-INVADER_PLAYER_SPEED:INVADER_PLAYER_SPEED;
    this.startWave();
  }

  private tick(dt:number){
    if(this.phase!=="play"){
      this.pause=Math.max(0,this.pause-dt);
      if(this.pause===0){if(this.phase==="lost")this.resetRun();else if(this.phase==="redeploy")this.finishRedeploy();else{this.wave++;this.startWave();}}
      return;
    }

    this.shield=Math.max(0,this.shield-dt);
    const alive=this.livingCount();
    const fleetSpeed=Math.min(88,(20+(INVADER_COUNT-alive)*.8)+(this.wave-1)*2.2);
    this.fleetX+=this.direction*fleetSpeed*dt;
    if(this.fleetX<=ALIEN_LEFT_MIN){this.fleetX=ALIEN_LEFT_MIN;this.direction=1;this.fleetY+=11;}
    else if(this.fleetX>=ALIEN_LEFT_MAX){this.fleetX=ALIEN_LEFT_MAX;this.direction=-1;this.fleetY+=11;}
    if(this.fleetY+(INVADER_ROWS-1)*ALIEN_ROW_STEP+ALIEN_SIZE>=352){this.redeploy();return;}

    this.thinkTimer-=dt;if(this.thinkTimer<=0)this.think();
    this.turnCooldown-=dt;
    if(this.turnCooldown<=0)this.chooseDirection();
    // Check after ordinary steering too: a newly selected aim must never send
    // the ship into a bullet lane merely because its turn cooldown expired.
    this.evadeIncoming();
    this.playerX=clamp(this.playerX+this.playerVelocity*dt,22,618);
    // A boundary contact is only a floating-point guard; direction planning
    // normally turns early enough that the ship never needs to park at a wall.
    if(this.playerX===22&&this.playerVelocity<0){this.playerVelocity=INVADER_PLAYER_SPEED;this.turnCooldown=Math.max(.48,this.turnCooldown);}
    if(this.playerX===618&&this.playerVelocity>0){this.playerVelocity=-INVADER_PLAYER_SPEED;this.turnCooldown=Math.max(.48,this.turnCooldown);}

    this.shootTimer-=dt;
    if(this.shootTimer<=0&&!this.shots.some(shot=>!shot.enemy)){
      this.shots.push({x:this.playerX,y:360,enemy:false});
      this.shootTimer=.36+this.random()*.28;
    }
    this.enemyTimer-=dt;
    const enemyShots=this.shots.filter(shot=>shot.enemy).length;
    if(this.enemyTimer<=0&&enemyShots<3&&alive>0){
      const shooters=this.lowestShooters(),index=shooters[Math.floor(this.random()*shooters.length)],alien=this.alien(index);
      this.shots.push({x:alien.x+ALIEN_SIZE/2+(this.random()-.5)*30,y:alien.y+ALIEN_SIZE,enemy:true});
      this.enemyTimer=.78+this.random()*1.25;
    }

    const remaining:InvaderShot[]=[];
    for(const shot of this.shots){
      shot.y+=shot.enemy?(176+this.wave*5)*dt:-(310+this.wave*7)*dt;
      let consumed=false;
      if(shot.enemy){
        if(shot.y>=350&&shot.y<=384&&Math.abs(shot.x-this.playerX)<=20){
          consumed=true;
          if(this.shield===0){this.lives--;this.shield=.62;if(this.lives<=0){this.lose();return;}}
        }
      }else{
        for(let index=0;index<this.alive.length;index++)if(this.alive[index]){
          const alien=this.alien(index);
          if(shot.x>=alien.x-2&&shot.x<=alien.x+ALIEN_SIZE+2&&shot.y>=alien.y-3&&shot.y<=alien.y+ALIEN_SIZE){
            this.alive[index]=false;this.score+=[30,20,20,10,10][alien.row];
            this.best=Math.max(this.best,this.score);consumed=true;break;
          }
        }
      }
      if(!consumed&&shot.y>=5&&shot.y<=395)remaining.push(shot);
    }
    this.shots=remaining;
    if(this.livingCount()===0){this.phase="wave";this.pause=1;this.shots=[];}
  }

  step(dt:number){
    let remaining=clamp(Number.isFinite(dt)?dt:0,0,.1);
    // Sixty physics steps per second still keep a fast shot well inside its
    // collision width while halving calculation work on the Pi 4.
    while(remaining>0){const slice=Math.min(remaining,1/60);this.tick(slice);remaining-=slice;}
  }
}
