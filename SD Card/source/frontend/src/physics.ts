export type Ball={x:number;y:number;vx:number;vy:number;r:number};
// Uniform-density disks: mass proportional to area. Elastic frictionless impacts.
export function collide(a:Ball,b:Ball) {
  const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy);
  if(d>=a.r+b.r || d<1e-9)return;
  const nx=dx/d,ny=dy/d,ia=1/(a.r*a.r),ib=1/(b.r*b.r);
  const overlap=a.r+b.r-d;
  a.x-=nx*overlap*ia/(ia+ib);a.y-=ny*overlap*ia/(ia+ib);
  b.x+=nx*overlap*ib/(ia+ib);b.y+=ny*overlap*ib/(ia+ib);
  const closing=(a.vx-b.vx)*nx+(a.vy-b.vy)*ny;
  if(closing<=0)return;
  const impulse=2*closing/(ia+ib);
  a.vx-=impulse*ia*nx;a.vy-=impulse*ia*ny;
  b.vx+=impulse*ib*nx;b.vy+=impulse*ib*ny;
}
export function stepBalls(balls:Ball[],dt:number,width=700,height=430):Ball[] {
  const next=balls.map(b=>({...b}));
  const count=Math.max(1,Math.ceil(dt/(1/240))),h=dt/count;
  for(let k=0;k<count;k++){
    for(const b of next){b.x+=b.vx*h;b.y+=b.vy*h;}
    for(let i=0;i<next.length;i++)for(let j=i+1;j<next.length;j++)collide(next[i],next[j]);
    for(const b of next){
      if(b.x<b.r){b.x=b.r;b.vx=Math.abs(b.vx);}else if(b.x>width-b.r){b.x=width-b.r;b.vx=-Math.abs(b.vx);}
      if(b.y<b.r){b.y=b.r;b.vy=Math.abs(b.vy);}else if(b.y>height-b.r){b.y=height-b.r;b.vy=-Math.abs(b.vy);}
    }
  }
  return next;
}
export type Pendulum={pivot:number;length:number;angle:number;omega:number;r:number};
export function createPendulums(random=Math.random):Pendulum[] {
  // Randomness supplies initial conditions only; physics drives every later frame.
  return Array.from({length:9},(_,i)=>({
    pivot:110+i*60,length:215+random()*50,angle:0,
    omega:(random()<.5?-1:1)*(.14+random()*.24),r:17,
  }));
}
export const bob=(p:Pendulum)=>({x:p.pivot+Math.sin(p.angle)*p.length,y:50+Math.cos(p.angle)*p.length});
export function stepPendulums(previous:Pendulum[],dt:number):Pendulum[] {
  const next=previous.map(p=>({...p}));
  const count=Math.max(1,Math.ceil(dt/(1/480))),h=dt/count,g=420;
  for(let k=0;k<count;k++){
    // Velocity Verlet avoids the energy gain of explicit Euler integration.
    for(const p of next){p.omega-=.5*h*g/p.length*Math.sin(p.angle);p.angle+=h*p.omega;p.omega-=.5*h*g/p.length*Math.sin(p.angle);}
    for(let i=0;i<next.length;i++)for(let j=i+1;j<next.length;j++){
      const a=next[i],b=next[j],pa=bob(a),pb=bob(b),dx=pb.x-pa.x,dy=pb.y-pa.y,d=Math.hypot(dx,dy);
      if(d>=a.r+b.r || d<1e-9)continue;
      const nx=dx/d,ny=dy/d;
      const ta=Math.cos(a.angle)*nx-Math.sin(a.angle)*ny,tb=Math.cos(b.angle)*nx-Math.sin(b.angle)*ny;
      const ia=1/(a.r*a.r),ib=1/(b.r*b.r),effective=ta*ta*ia+tb*tb*ib;
      if(effective<1e-12)continue;
      const closing=a.omega*a.length*ta-b.omega*b.length*tb;
      if(closing>0){const impulse=2*closing/effective;a.omega-=impulse*ia*ta/a.length;b.omega+=impulse*ib*tb/b.length;}
      // Project tiny numerical overlaps along the permitted circular paths.
      const correction=(a.r+b.r-d)/effective;
      a.angle-=correction*ia*ta/a.length;b.angle+=correction*ib*tb/b.length;
    }
  }
  return next;
}
