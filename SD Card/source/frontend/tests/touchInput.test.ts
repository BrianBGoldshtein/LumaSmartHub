import test from "node:test";
import assert from "node:assert/strict";
import {editInput,validInput,coordinates} from "../src/touchInput.ts";
import {setupLink,setupTheme} from "../src/setupTheme.ts";
import {googleCallbackMessage} from "../src/googleSetupState.ts";

test("touch typing supports insertion, replacing a selection, backspace and clearing",()=>{
  assert.deepEqual(editInput("Stanfor","d"),{value:"Stanford",caret:8});
  assert.deepEqual(editInput("Stnford","a",2,2),{value:"Stanford",caret:3});
  assert.deepEqual(editInput("Home","Office",0,4),{value:"Office",caret:6});
  assert.deepEqual(editInput("Stanford","Backspace",4,4),{value:"Staford",caret:3});
  assert.deepEqual(editInput("Home","Backspace",0,4),{value:"",caret:0});
  assert.deepEqual(editInput("Home","Clear"),{value:"",caret:0});
  assert.equal(editInput("🌞","Backspace").value,"");
});
test("PIN input is digits only and cannot overrun its length from the touch keypad",()=>{
  assert.equal(editInput("12345678","9",8,8,8,"digits").value,"12345678");
  assert.equal(editInput("12","a",2,2,8,"digits").value,"12");
  assert.equal(editInput("12"," ",2,2,8,"digits").value,"12");
  assert.equal(validInput("1234","digits"),true);
  assert.equal(validInput("１２３４","digits"),false);
});
test("coordinate entry permits partial negative decimals but not duplicate separators",()=>{
  for(const text of ["","-","-0.","-122.17",".5"])assert.equal(validInput(text,"decimal"),true);
  for(const text of ["1-2","1.2.3","+2","2e4","Infinity"])assert.equal(validInput(text,"decimal"),false);
  assert.equal(editInput("-122.1",".",6,6,14,"decimal").value,"-122.1");
});
test("coordinate submission requires a valid bounded pair or two blanks",()=>{
  assert.deepEqual(coordinates(" ",""),{latitude:null,longitude:null});
  assert.deepEqual(coordinates("37.42","-122.17"),{latitude:37.42,longitude:-122.17});
  assert.deepEqual(coordinates("0","0"),{latitude:0,longitude:0});
  for(const [lat,lon] of [["1",""],["-","-1"],[".","0"],["91","0"],["0","-181"],["Infinity","0"]])assert.throws(()=>coordinates(lat,lon));
});
test("setup links preserve demo themes without changing production configuration",()=>{
  assert.equal(setupTheme("neon-grid"),"neon-grid");assert.equal(setupTheme("unknown"),"luma-glass");
  assert.equal(setupLink(true,"hearth","google"),"/?demo=1&theme=hearth&setup=google");
  assert.equal(setupLink(false,"hearth","device"),"/?setup=device");
  assert.equal(setupLink(false,"hearth"),"/");
});

test("Google callback recovery uses only a fixed notice, never provider/query text",()=>{
  assert.match(googleCallbackMessage("1"),/Try again/);
  for(const value of [null,undefined,"access_denied: private-data","0",1])assert.equal(googleCallbackMessage(value),"");
});
