import test from 'node:test';
import assert from 'node:assert/strict';
import {taskPages,taskDueLabel} from '../src/todoState.ts';
test('all tasks are reachable without shrinking the three-row design',()=>{
  const tasks=Array.from({length:14},(_,i)=>({id:String(i)})) as Parameters<typeof taskPages>[0];
  const ids=Array.from({length:5},(_,page)=>taskPages(tasks,page).items.map(item=>item.id)).flat();
  assert.equal(new Set(ids).size,14);
  assert.equal(taskPages(tasks,5).index,0);
  assert.equal(taskPages(tasks,-1).index,4);
  assert.deepEqual(taskPages([],8),{index:0,count:1,total:0,items:[]});
});
test('completed tasks never consume a to-do page or appear in its count',()=>{
  const tasks=Array.from({length:8},(_,i)=>({id:String(i),completed:i<5})) as Parameters<typeof taskPages>[0];
  assert.deepEqual(taskPages(tasks,0).items.map(item=>item.id),['5','6','7']);
  assert.deepEqual(taskPages(tasks,1),{index:0,count:1,total:3,items:tasks.slice(5)});
  assert.deepEqual(taskPages(tasks.map(item=>({...item,completed:true})),0),{index:0,count:1,total:0,items:[]});
});
test('due-date labels do not subtract a second timezone offset',()=>{
  assert.equal(taskDueLabel('2026-09-26','2026-09-26'),'Due today');
  assert.equal(taskDueLabel('2026-09-27','2026-09-26'),'Due Sep 27');
  assert.equal(taskDueLabel(undefined,'2026-09-26'),'');
});
