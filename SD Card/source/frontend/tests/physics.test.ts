import test from "node:test";
import assert from "node:assert/strict";
import {collide,createPendulums,stepBalls,stepPendulums,bob} from "../src/physics.ts";
const near=(a:number,b:number,tolerance=1e-8)=>assert.ok(Math.abs(a-b)<tolerance,`${a} != ${b}`);
test("pendulums start vertical with bounded randomized lengths and velocities",()=>{
  let seed=42;const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const initial=createPendulums(random);assert.equal(initial.length,9);
  for(const p of initial){assert.equal(p.angle,0);near(bob(p).x,p.pivot);assert.ok(p.length>=215 && p.length<=265);assert.ok(Math.abs(p.omega)>=.14 && Math.abs(p.omega)<=.38);}
  assert.ok(new Set(initial.map(p=>p.length)).size>1);assert.ok(initial.some(p=>p.omega<0));assert.ok(initial.some(p=>p.omega>0));
  const next=stepPendulums(initial,.032);assert.ok(next.some(p=>p.angle!==0));assert.ok(initial.every(p=>p.angle===0));
  next.forEach((p,i)=>assert.equal(p.length,initial[i].length));
});
test("unequal-mass oblique elastic collision conserves both momentum components and energy",()=>{
  const a={x:0,y:0,vx:4,vy:3,r:2},b={x:2,y:2,vx:-2,vy:1,r:1};
  const momentum=()=>[a.r*a.r*a.vx+b.r*b.r*b.vx,a.r*a.r*a.vy+b.r*b.r*b.vy];
  const energy=()=>a.r*a.r*(a.vx*a.vx+a.vy*a.vy)+b.r*b.r*(b.vx*b.vx+b.vy*b.vy);
  const before=momentum(),e=energy();collide(a,b);
  momentum().forEach((v,i)=>near(v,before[i]));near(energy(),e);
});
test("separating balls do not get a second collision impulse",()=>{
  const a={x:0,y:0,vx:-1,vy:0,r:2},b={x:3,y:0,vx:1,vy:0,r:2};
  collide(a,b);near(a.vx,-1);near(b.vx,1);
});
test("closed box retains kinetic energy over sustained collisions",()=>{
  let balls=[{x:100,y:100,vx:130,vy:70,r:20},{x:200,y:120,vx:-90,vy:40,r:30}];
  const energy=()=>balls.reduce((sum,b)=>sum+b.r*b.r*(b.vx*b.vx+b.vy*b.vy),0),initial=energy();
  for(let i=0;i<2000;i++)balls=stepBalls(balls,.032);
  near(energy()/initial,1);
});
test("unconstrained pendulum integration preserves mechanical energy",()=>{
  let p=[{pivot:100,length:220,angle:.3,omega:0,r:17}];
  const energy=()=>.5*(p[0].length*p[0].omega)**2+420*p[0].length*(1-Math.cos(p[0].angle));
  const initial=energy();for(let i=0;i<2000;i++)p=stepPendulums(p,.032);
  near(energy()/initial,1,1e-5);near(Math.hypot(bob(p[0]).x-100,bob(p[0]).y-50),220);
});
test("hanging equal-mass balls transfer tangential velocity on contact",()=>{
  const p=stepPendulums([{pivot:100,length:220,angle:0,omega:1,r:17},{pivot:134,length:220,angle:0,omega:0,r:17}],.00001);
  near(p[0].omega,0,1e-7);near(p[1].omega,1,1e-7);
});
