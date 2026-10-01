import test from 'node:test';
import assert from 'node:assert/strict';
import {taskPages,taskDueLabel} from '../src/todoState.ts';
test('all tasks are reachable without shrinking the three-row design',()=>{
  const tasks=Array.from({length:14},(_,i)=>({id:String(i)})) as Parameters<typeof taskPages>[0];
  const ids=Array.from({length:5},(_,page)=>taskPages(tasks,page).items.map(item=>item.id)).flat();
  assert.equal(new Set(ids).size,14);
  assert.equal(taskPages(tasks,5).index,0);
  assert.equal(taskPages(tasks,-1).index,4);
  assert.deepEqual(taskPages([],8),{index:0,count:1,total:0,items:[],completedOnly:false});
});
test('outstanding tasks precede completed tasks, each by nearest due date',()=>{
  const tasks=[
    {id:'done-later',summary:'Done later',due_date:'2026-10-03',completed:true},
    {id:'open-later',summary:'Open later',due_date:'2026-10-02',completed:false},
    {id:'done-soon',summary:'Done soon',due_date:'2026-10-01',completed:true},
    {id:'open-soon',summary:'Open soon',due_date:'2026-10-01',completed:false},
  ] as Parameters<typeof taskPages>[0];
  assert.deepEqual(taskPages(tasks,0).items.map(item=>item.id),['open-soon','open-later']);
  assert.equal(taskPages(tasks,0).completedOnly,false);
  assert.deepEqual(taskPages(tasks,1).items.map(item=>item.id),['done-soon','done-later']);
  assert.equal(taskPages(tasks,1).completedOnly,true);
  assert.equal(taskPages(tasks,1).total,4);
});
test('completed-only pages remain visible and rotate back to outstanding pages',()=>{
  const tasks=Array.from({length:8},(_,i)=>({id:String(i),summary:String(i),completed:i<5})) as Parameters<typeof taskPages>[0];
  assert.deepEqual(taskPages(tasks,0).items.map(item=>item.id),['5','6','7']);
  assert.deepEqual(taskPages(tasks,1).items.map(item=>item.id),['0','1','2']);
  assert.deepEqual(taskPages(tasks,2).items.map(item=>item.id),['3','4']);
  assert.equal(taskPages(tasks,3).index,0);
  assert.equal(taskPages(tasks.map(item=>({...item,completed:true})),0).completedOnly,true);
});
test('due-date labels do not subtract a second timezone offset',()=>{
  assert.equal(taskDueLabel('2026-09-26','2026-09-26'),'Due today');
  assert.equal(taskDueLabel('2026-09-27','2026-09-26'),'Due Sep 27');
  assert.equal(taskDueLabel(undefined,'2026-09-26'),'');
});
