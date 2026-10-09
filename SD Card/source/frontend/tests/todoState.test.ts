import test from 'node:test';
import assert from 'node:assert/strict';
import {taskPages,taskDueLabel,deadlineStatus} from '../src/todoState.ts';

test('dense shared panels use two tasks per slide without losing ordering or completion groups',()=>{
  const tasks=Array.from({length:9},(_,i)=>({id:String(i),summary:String(i),due_date:`2026-10-${String(i+10).padStart(2,'0')}`,completed:i>=5})) as Parameters<typeof taskPages>[0];
  const pages=Array.from({length:5},(_,page)=>taskPages(tasks,page,2));
  assert.deepEqual(pages.flatMap(page=>page.items.map(task=>task.id)),tasks.map(task=>task.id));
  assert.ok(pages.every(page=>page.items.length<=2));
  assert.deepEqual(pages.map(page=>page.completedOnly),[false,false,false,true,true]);
  for(const bad of [0,4,1.5])assert.throws(()=>taskPages(tasks,0,bad));
});
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
test('deadline colors progress from urgent red through yellow to green in every theme',()=>{
  for(const theme of ['luma-glass','hearth','neon-grid'] as const){
    const today='2026-10-01';
    const statuses=['2026-09-30','2026-10-01','2026-10-02','2026-10-04','2026-10-05','2026-10-08','2026-10-09']
      .map(date=>deadlineStatus(date,today,theme));
    assert.equal(statuses[0].kind,'overdue');
    assert.equal(statuses[1].kind,'urgent');
    assert.equal(statuses[2].kind,'urgent');
    assert.equal(statuses[3].kind,'approaching');
    assert.equal(statuses[6].kind,'distant');
    assert.equal(statuses[1].color,statuses[2].color);
    assert.equal(statuses[5].color,statuses[6].color);
    const hue=(color:string)=>Number(color.match(/ ([0-9]+)\)$/)?.[1]);
    assert.ok(hue(statuses[2].color)<hue(statuses[3].color));
    assert.ok(hue(statuses[3].color)<hue(statuses[5].color));
    assert.match(statuses[3].label,/Due in 3 days/);
    assert.match(statuses[0].label,/Overdue by 1 day/);
  }
});
test('deadline day arithmetic ignores DST hours and rejects invalid dates',()=>{
  assert.equal(deadlineStatus('2026-11-02','2026-11-01','hearth').daysUntil,1);
  assert.equal(deadlineStatus('2027-03-15','2027-03-14','hearth').daysUntil,1);
  assert.equal(deadlineStatus('2026-02-30','2026-02-28','hearth').kind,'unknown');
  assert.equal(deadlineStatus(undefined,'2026-02-28','hearth').label,'Deadline unavailable');
});
