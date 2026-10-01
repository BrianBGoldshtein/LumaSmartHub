"""Reproducibly train Luma's tiny offline query classifier (stdlib only).

Run from backend/: python train_voice_model.py. No private user samples.
This is a shallow supervised neural embedding-bag/softmax model, not an LLM.
"""
from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
import random
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
from luma.voice_library import QUERY_PHRASES
from luma.voice_model import FEATURES, features


EXTRA = {
    'weather_now':['tell me the current weather','how warm is it outside','tell me outside temperature'],
    'weather_today':['tell me todays forecast','give me the forecast for today','how is it looking outside today'],
    'weather_tomorrow':['tell me tomorrows forecast','how will the weather be tomorrow','give me the forecast for tomorrow'],
    'weather_afternoon':['forecast for this afternoon','how is the afternoon looking'],
    'weather_evening':['forecast for this evening','how is tonight looking'],
    'rain_today':['any rain expected today','will i need an umbrella today'],
    'rain_tomorrow':['any rain expected tomorrow','will i need an umbrella tomorrow'],
    'rain_timing':['what time is rain expected','tell me when rain starts'],
    'high_today':['tell me todays high','maximum temperature today'],
    'low_today':['tell me todays low','minimum temperature today'],
    'high_tomorrow':['tell me tomorrows high','maximum temperature tomorrow'],
    'low_tomorrow':['tell me tomorrows low','minimum temperature tomorrow'],
    'jacket':['should i wear a coat','is it jacket weather'],
    'next_event':['tell me my next appointment','what meeting comes next','whats coming up next','what time does my next class start','when does my next meeting start'],
    'calendar_today':['read out todays events','tell me my plans today','what does my day look like'],
    'remaining_today':['tell me what events i have left today','anything else coming up today','what remains on my schedule today'],
    'calendar_tomorrow':['read out tomorrows events','tell me my plans tomorrow','what does tomorrow look like'],
    'calendar_week':['read out this weeks events','tell me my plans this week'],
    'ongoing':['what meeting am i in','whats on right now'],
    'next_location':['tell me the location of my next event','where is my next meeting'],
    'free_time':['do i have any free time','how much time until my next meeting','when do i have a break','tell me my next free block'],
    'tasks_today':['tell me my to dos today','list my outstanding tasks','what do i need to do today'],
    'tasks_due':['tell me todays due tasks','which tasks have a due date today'],
    'tasks_soon':['list tasks due soon','what tasks are coming due'],
    'tasks_overdue':['list overdue tasks','which tasks are late'],
    'tasks_completed':['list completed tasks','what tasks are finished'],
    'time':['tell me what time it is','give me the current time'],
    'date':['tell me todays date','give me the current date'],
    'timer_status':['check my timer','tell me how much time remains on timer'],
    'phone_status':['tell me if my iphone is connected','check phone connection'],
    'privacy_status':['tell me if privacy is on','why is luma in private standby'],
    'internet_status':['check internet connection','tell me if wifi works'],
    'sync_status':['check calendar sync','tell me if my data is current'],
    'next_departure':['tell me the next bus departure','when does my bus leave'],
    'help':['list the things you can do','give me command examples'],
}

ACTION_PHRASES = {
    'action:home':['open home','take me home','show my dashboard','display home screen'],
    'action:weather':['open weather','pull up weather','take me to the forecast','display weather screen'],
    'action:agenda':['open calendar','pull up my agenda','take me to my schedule','display calendar screen'],
    'action:todos':['open my tasks','pull up my to do list','display tasks screen'],
    'action:ambient':['open ambient','show the animations','display ambient screen'],
    'action:countdowns':['open countdowns','display countdown screen','show important dates'],
    'action:transit':['open transit','show bus times','display transit screen'],
    'action:next_page':['move to the next screen','go to the next page','advance the display'],
    'action:previous_page':['go to the prior screen','return to previous page','move back one page'],
    'action:brightness':['open brightness control','let me adjust brightness','bring up the brightness slider'],
    'action:volume':['open volume control','let me adjust volume','bring up the volume slider'],
    'action:glass':['switch to glass design','use the clean theme','make the display glass'],
    'action:hearth':['switch to cabin design','use the wooden theme','make the display hearth'],
    'action:arcade':['switch to arcade design','use the neon theme','make the display pixelated'],
}


def training_rows():
    rows=[]
    for label,phrases in QUERY_PHRASES.items():
        for phrase in (*phrases,*EXTRA.get(label,())):
            phrase=phrase.casefold().replace('’',"'").replace("what's",'what is')
            rows.append((label,phrase))
            if not phrase.startswith('please '):rows.append((label,'please '+phrase))
    for label,phrases in ACTION_PHRASES.items():
        for phrase in phrases:
            rows.append((label,phrase))
            rows.append((label,'please '+phrase))
    return rows


def train():
    labels=sorted([*QUERY_PHRASES,*ACTION_PHRASES])
    rows=training_rows()
    rng=random.Random(2309)
    weights={label:defaultdict(float) for label in labels}
    bias={label:0.0 for label in labels}
    for epoch in range(95):
        rng.shuffle(rows)
        rate=.55/(1+epoch/35)
        for target,text in rows:
            indices=features(text)
            if not indices:continue
            norm=math.sqrt(len(indices))
            scores=[bias[label]+sum(weights[label][index] for index in indices)/norm for label in labels]
            highest=max(scores)
            exp=[math.exp(score-highest) for score in scores]
            total=sum(exp)
            for label,score in zip(labels,exp):
                error=(int(label==target)-score/total)*rate
                bias[label]+=error*.15
                for index in indices:
                    weights[label][index]+=error/norm
    magnitude=max(abs(value) for row in weights.values() for value in row.values())
    scale=127/magnitude
    data={'version':1,'features':FEATURES,'scale':scale,'labels':labels,
          'bias':{label:round(bias[label]*scale) for label in labels},
          'weights':{label:{str(index):round(value*scale) for index,value in sorted(weights[label].items())
                            if abs(value*scale)>=.5} for label in labels}}
    destination=Path(__file__).resolve().parent/'src'/'luma'/'voice_intents.json'
    destination.write_text(json.dumps(data,separators=(',',':'),sort_keys=True),encoding='utf-8')
    print(f'{len(labels)} intents, {len(rows)} authored/augmented phrases, {destination.stat().st_size} bytes')


if __name__=='__main__':train()
