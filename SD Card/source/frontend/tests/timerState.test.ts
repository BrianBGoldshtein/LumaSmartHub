import test from 'node:test';
import assert from 'node:assert/strict';
import {idleTimer,timerRemaining,timerText,previewTimerCommand} from '../src/timerState.ts';

test('timer display uses a monotonic sample and rounds only for display',()=>{
 const timer=previewTimerCommand(idleTimer,'start_timer',{minutes:1},0,'first');
 assert.equal(timerText(timerRemaining(timer,1.2)),'0:59');
 assert.equal(timerText(timerRemaining(timer,61)),'0:00');
 assert.equal(timerText(14400),'240:00');
 assert.equal(timerRemaining({...timer,status:'paused'},300),60);
 assert.equal(timerRemaining(timer,-1),60);
});
test('preview pause, resume and cancel are isolated state transitions',()=>{
 let timer=previewTimerCommand(idleTimer,'start_timer',{minutes:25,label:'Focus'},0,'first');
 timer=previewTimerCommand(timer,'pause_timer',null,1450,'unused');
 assert.equal(timer.status,'paused');assert.equal(timer.remaining_seconds,1450);
 timer=previewTimerCommand(timer,'resume_timer',null,1450,'unused');
 assert.equal(timer.status,'running');
 assert.deepEqual(previewTimerCommand(timer,'cancel_timer',null,1400,'unused'),idleTimer);
 assert.equal(idleTimer.status,'idle');
});
test('timer replacement checks the active run, not merely a boolean',()=>{
 const timer=previewTimerCommand(idleTimer,'start_timer',{minutes:5},0,'first');
 assert.throws(()=>previewTimerCommand(timer,'start_timer',{minutes:10},100,'second'));
 assert.throws(()=>previewTimerCommand(timer,'start_timer',{minutes:10,replace_id:'stale'},100,'second'));
 assert.equal(previewTimerCommand(timer,'start_timer',{minutes:10,replace_id:'first'},100,'second').id,'second');
 for(const minutes of [0,241,1.5,NaN,Infinity])assert.throws(()=>previewTimerCommand(idleTimer,'start_timer',{minutes},0,'bad'));
});
