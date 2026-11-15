#!/usr/bin/env python3
"""ASTRA v1 synthetic spaceflight-informed longitudinal data generator.
Purely synthetic records, NOT NASA astronaut patient data. All params explicit.
Requires numpy; uses csv and json from Python standard library.
"""
from __future__ import annotations
import csv, json, hashlib, math, statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
SEED=20261114
rng=np.random.default_rng(SEED)
MISSION_ID='ASTRA-SYN-90D-01'
START=datetime(2040,1,1,tzinfo=timezone.utc)
DAYS=90
REPLAY_START=45 # days 1..45 visible initially, days 46..90 hidden
ATM_PRESSURE_MMHG=760.0 # assumed, not measured; needed to derive ppm from mmHg

PROFILES=[
    dict(crew_id='AST-001',display_name='Daniel Okafor',role='Flight Engineer',age_years=37,rest_hr_ref_bpm=63,sys_ref_mmhg=115,dia_ref_mmhg=74,sleep_tendency_h=7.22,activity_pref='resistance',baseline_stress=1.10),
    dict(crew_id='AST-002',display_name='Samir Rahman',role='Science Specialist',age_years=35,rest_hr_ref_bpm=68,sys_ref_mmhg=119,dia_ref_mmhg=77,sleep_tendency_h=7.34,activity_pref='mixed',baseline_stress=1.22),
    dict(crew_id='AST-003',display_name='Hana Tanaka',role='Crew Medical Officer',age_years=42,rest_hr_ref_bpm=57,sys_ref_mmhg=111,dia_ref_mmhg=71,sleep_tendency_h=7.44,activity_pref='endurance',baseline_stress=1.00),
    dict(crew_id='AST-004',display_name='Maya Vega',role='Commander',age_years=44,rest_hr_ref_bpm=61,sys_ref_mmhg=117,dia_ref_mmhg=75,sleep_tendency_h=7.40,activity_pref='mixed',baseline_stress=1.13),
]

METRICS={
'resting_heart_rate':('bpm','Morning wearable resting estimate'),
'exercise_heart_rate':('bpm','Recorded during planned exercise, not comparable to resting'),
'recovery_heart_rate':('bpm','Approximate HR measured 20 minutes after exercise'),
'sleep_duration':('h','Nightly wearable/self-report composite'),
'sleep_quality':('score_0_4','Voluntary perceived sleep quality; 4 best'),
'fatigue':('score_0_4','Voluntary fatigue rating; 4 most fatigued'),
'mood':('score_0_4','Voluntary mood; 4 most positive'),
'perceived_stress':('score_0_4','Voluntary stress; 4 highest'),
'headache':('score_0_4','Voluntary headache; 0 means no symptom reported'),
'systolic_bp':('mmHg','Intermittent cuff measurement'),
'diastolic_bp':('mmHg','Intermittent cuff measurement paired with systolic'),
'body_temperature':('degC','Intermittent thermometer reading'),
'spo2':('percent','Intermittent finger pulse oximeter reading'),
'exercise_duration':('min','Voluntary exercise session duration'),
'cabin_co2_partial_pressure':('mmHg','CO2 partial pressure, primary cabin CO2 value'),
'cabin_co2_concentration':('ppm','Derived from assumed constant 760 mmHg total pressure'),
'cabin_temperature':('degC','Cabin temperature'),
'cabin_relative_humidity':('percent','Cabin relative humidity'),
}

def ts(day,h=0,m=0):
    return (START+timedelta(days=day-1,hours=h,minutes=m)).isoformat(timespec='seconds').replace('+00:00','Z')

def clamp(x,lo,hi):return min(hi,max(lo,float(x)))
def round2(x):return round(float(x),2)

def write_csv(p,rows,fields):
    with (HERE/p).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def unique_id(prefix,k):return f'{prefix}-{k:07d}'

OBS_FIELDS=['observation_id','mission_id','crew_id','subject_id','scope','timestamp_utc','mission_day','metric','value','unit','activity_context','source','provenance','quality','missing_reason','privacy','share_cabin_context','note']
obs=[]
sequence=0

def add(metric,day,h=0,m=0,crew_id='',value=None,activity='unspecified',source='synthetic_model',quality='VALID',missing_reason='',privacy='crew',share=False,note=''):
    global sequence
    sequence+=1
    is_cabin=metric.startswith('cabin_')
    target='CABIN-01' if is_cabin else crew_id
    obs.append(dict(observation_id=unique_id('SIM',sequence),mission_id=MISSION_ID,crew_id='' if is_cabin else crew_id,
       subject_id=target,scope='cabin' if is_cabin else 'person',timestamp_utc=ts(day,h,m),mission_day=day,
       metric=metric,value='' if value is None else value,unit=METRICS[metric][0],activity_context=activity,
       source=source,provenance='SYNTHETIC',quality=quality,missing_reason=missing_reason,
       privacy='shared_environment' if is_cabin else privacy,share_cabin_context=str(bool(share)).lower(),note=note))

# Cabin conditions: correlated fluctuations, circadian waves, sustained excursion days 61-63,
# gap day 56 06:00..14:00, and occasional isolated missing samples.
cabin_rows=[]
co2_state=1.42
cabtemp_state=22.3
humidity_state=45.0
for d in range(1,DAYS+1):
  for h in range(24):
    co2_state=.90*co2_state+.10*1.37+rng.normal(0,.065)
    cabtemp_state=.88*cabtemp_state+.12*22.6+rng.normal(0,.13)
    humidity_state=.88*humidity_state+.12*44.0+rng.normal(0,.9)
    ppco2=clamp(co2_state+0.22*math.sin(2*math.pi*(h-5)/24),.72,2.65)
    # First noticeable excursion late day 61; sustained but non-monotonic rise/decay
    if d==61 and h>=18: ppco2+=.55 +.42*(h-18)/5
    if d==62: ppco2+=2.0+0.35*math.sin(2*math.pi*h/24)
    if d==63: ppco2+=max(0,1.7-1.7*h/23)
    ppco2=clamp(ppco2,.70,4.3)
    ctemp=clamp(cabtemp_state+0.30*math.sin(2*math.pi*(h-6)/24),19.5,26.2)
    rh=clamp(humidity_state,27,64)
    gap = d==56 and 6<=h<=14
    readings=[('cabin_co2_partial_pressure',round2(ppco2),'synthetic_cabin_co2_sensor'),
              ('cabin_co2_concentration',round(int(ppco2/ATM_PRESSURE_MMHG*1_000_000)),'synthetic_cabin_co2_sensor_derived'),
              ('cabin_temperature',round2(ctemp),'synthetic_cabin_temp_sensor'),
              ('cabin_relative_humidity',round2(rh),'synthetic_cabin_humidity_sensor')]
    for metric,value,source in readings:
        if gap or rng.random()<.002:
           add(metric,d,h,value=None,source=source,quality='MISSING',missing_reason='TELEMETRY_GAP')
        else: add(metric,d,h,value=value,source=source)

# Daily latent behavioral state with autocorrelation; astronaut-specific parameters.
# Deliberate sleep-disruption days 73-79 for Samir; common crew sleep disruption days 59-60.
# Single-day isolated headache episodes are permitted outside the cabin event.
for profile in PROFILES:
    c=profile['crew_id']; baseline_hr=profile['rest_hr_ref_bpm'];stress_ar=0; hr_ar=0; sleep_ar=0
    for d in range(1,DAYS+1):
        stress_ar=.68*stress_ar+rng.normal(0,.40)
        sleep_ar=.45*sleep_ar+rng.normal(0,.48)
        hr_ar=.58*hr_ar+rng.normal(0,2.0)
        if 73<=d<=79 and c=='AST-002': stress_ar+=.18
        sleep_modifier=(-1.70 if 73<=d<=79 and c=='AST-002' else 0)
        sleep_modifier+=(-.58 if d in (59,60) else 0)
        # Approximate 7.3h in-flight sleep with crew variance; published NASA aggregate is reference.
        sleep_h=clamp(profile['sleep_tendency_h']+sleep_ar+ rng.normal(0,1.03)+sleep_modifier,3.8,9.5)
        sleep_h=round2(sleep_h)
        sleep_debt=max(0,7.1-sleep_h)
        stress_cont=clamp(profile['baseline_stress']+.60*stress_ar+.42*sleep_debt,0,4)
        fatigue_cont=clamp(.55+.72*sleep_debt+.42*stress_ar+rng.normal(0,.28),0,4)
        sleep_qual=int(clamp(round(3.35-.50*sleep_debt-.23*stress_cont+rng.normal(0,.52)),0,4))
        fatigue=int(clamp(round(fatigue_cont),0,4))
        mood=int(clamp(round(3.18-.26*stress_cont-.20*sleep_debt+rng.normal(0,.52)),0,4))
        stress=int(clamp(round(stress_cont),0,4))
        # Crew-specific adaptation shape is a small modelling assumption, not a published NASA effect size.
        adaptation=1.9*math.exp(-d/13.0)-0.5*math.exp(-d/60.0)
        hr_shift= (5.4*math.exp(-(d-56)**2/30.0) if c=='AST-004' else 0)
        if c=='AST-002' and 73<=d<=79: hr_shift+=4.5
        resthr=int(round(clamp(baseline_hr+hr_ar+1.5*sleep_debt+1.1*stress_cont+adaptation+hr_shift+rng.normal(0,1.45),43,112)))
        # daily sleep check-in, consent private; headache uses optional shared flag only when nonzero
        add('sleep_duration',d,7,30,c,sleep_h,'sleep','synthetic_actigraphy','VALID',privacy='private_health')
        for met,val in [('sleep_quality',sleep_qual),('fatigue',fatigue),('mood',mood),('perceived_stress',stress)]:
            add(met,d,7,35,c,val,'self_report','synthetic_self_report',privacy='private_health')
        # Strongly separated scripted cabin test case, deliberately does NOT encode causal attribution.
        headache=0;share=False
        if (c,d) in [('AST-001',62),('AST-003',62),('AST-003',63)]:
            headache=2 if d==62 else 1;share=True
        elif (c,d) in [('AST-002',24),('AST-004',41),('AST-001',80),('AST-002',76)]:
            headache=1
        elif rng.random()<.012:
            headache=1
        add('headache',d,7,37,c,headache,'self_report','synthetic_self_report',privacy='private_health',share=share,
            note=('Synthetic engineered cabin event: co-occurrence, NOT established causation' if share else ''))
        # Wearable morning reading + occasional dropout; no fabricated normal value.
        wear_gap=(c=='AST-004' and d in (67,68,69)) or rng.random()<.012
        add('resting_heart_rate',d,7,40,c,None if wear_gap else resthr,'rest','synthetic_wearable',
            'MISSING' if wear_gap else 'VALID','SENSOR_GAP' if wear_gap else '')
        # BP twice weekly on fixed scheduling + additional variable sampling; no fake continuous BP.
        if d%7 in (1,4) or (rng.random()<.05):
            sbp=int(round(clamp(profile['sys_ref_mmhg']+.43*(resthr-baseline_hr)+.80*stress_cont+rng.normal(0,5.3),91,146)))
            dbp=int(round(clamp(profile['dia_ref_mmhg']+.18*(resthr-baseline_hr)+.34*stress_cont+rng.normal(0,3.7),54,91)))
            if sbp-dbp<19:sbp=dbp+20
            add('systolic_bp',d,8,10,c,sbp,'rest','synthetic_bp_cuff')
            add('diastolic_bp',d,8,10,c,dbp,'rest','synthetic_bp_cuff')
        # Thermometer and oximeter intermittent, not daily fake continuous measurements.
        if d%3==0:
            temp=round2(clamp(36.57+rng.normal(0,.19)+(.12 if c=='AST-003' else 0),36.02,37.44))
            add('body_temperature',d,8,15,c,temp,'rest','synthetic_thermometer')
        if d%4==1:
            sp=int(round(clamp(97.8+rng.normal(0,.84),95,100)))
            add('spo2',d,8,20,c,sp,'rest','synthetic_pulse_oximeter')
        # Exercise six days weekly; occasional session skips; activity context explicit.
        if d%7!=0 and rng.random()>.065:
            if profile['activity_pref']=='endurance': intensity=clamp(rng.normal(.67,.12),.35,.92)
            elif profile['activity_pref']=='resistance': intensity=clamp(rng.normal(.57,.15),.28,.86)
            else:intensity=clamp(rng.normal(.61,.15),.32,.92)
            duration=int(round(clamp(rng.normal(80+10*intensity,16),35,130)))
            exhr=int(round(clamp(resthr+30+76*intensity+rng.normal(0,7),93,185)))
            recv=int(round(clamp(resthr+8+24*intensity+rng.normal(0,4),resthr+4,125)))
            add('exercise_duration',d,16,0,c,duration,'exercise','synthetic_activity_log')
            add('exercise_heart_rate',d,16,25,c,exhr,'exercise','synthetic_wearable')
            add('recovery_heart_rate',d,17,0,c,recv,'recovery','synthetic_wearable')

obs.sort(key=lambda o:(o['timestamp_utc'],o['subject_id'],o['metric']))
health=[r for r in obs if r['scope']=='person']
cabin=[r for r in obs if r['scope']=='cabin']
history=[r for r in obs if r['mission_day']<=REPLAY_START]
future=[r for r in obs if r['mission_day']>REPLAY_START]
write_csv('all_observations_FULL_ARCHIVE.csv',obs,OBS_FIELDS)
write_csv('health_observations.csv',health,OBS_FIELDS)
write_csv('cabin_environment_observations.csv',cabin,OBS_FIELDS)
write_csv('replay_history_DAY01_to_DAY45.csv',history,OBS_FIELDS)
write_csv('replay_future_HIDDEN_DAY46_to_DAY90.csv',future,OBS_FIELDS)
profile_fields=['crew_id','display_name','role','age_years','rest_hr_ref_bpm','sys_ref_mmhg','dia_ref_mmhg','sleep_tendency_h','activity_pref','baseline_stress']
write_csv('crew_profiles.csv',PROFILES,profile_fields)

# Convenience daily summary used only for inspection; no forward-filled missing readings.
idx=defaultdict(list)
for r in obs: idx[(r['crew_id'],r['mission_day'],r['metric'])].append(r)
def val(c,d,m):
    xs=idx.get((c,d,m),[])
    v=[str(x['value']) for x in xs if x['quality']=='VALID' and x['value']!='']
    return v[0] if v else ''
summary=[]
for p in PROFILES:
 for d in range(1,DAYS+1):
    c=p['crew_id'];summary.append(dict(crew_id=c,display_name=p['display_name'],mission_day=d,utc_date=ts(d)[:10],
       resting_hr_bpm=val(c,d,'resting_heart_rate'),exercise_hr_bpm=val(c,d,'exercise_heart_rate'),
       recovery_hr_bpm=val(c,d,'recovery_heart_rate'),sleep_hours=val(c,d,'sleep_duration'),
       sleep_quality_0_4=val(c,d,'sleep_quality'),fatigue_0_4=val(c,d,'fatigue'),mood_0_4=val(c,d,'mood'),
       stress_0_4=val(c,d,'perceived_stress'),headache_0_4=val(c,d,'headache'),systolic_mmhg=val(c,d,'systolic_bp'),
       diastolic_mmhg=val(c,d,'diastolic_bp'),body_temp_C=val(c,d,'body_temperature'),spo2_percent=val(c,d,'spo2'),
       exercise_minutes=val(c,d,'exercise_duration'),is_replay_future=str(d>REPLAY_START).lower()))
summary_fields=list(summary[0])
write_csv('crew_daily_summary_FOR_REVIEW.csv',summary,summary_fields)

source_rows=[
 {'source_id':'NASA-SLEEP','organization':'NASA/NTRS','title':'Astronaut Sleep Duration Varies by Timing of Scheduled Sleep','url':'https://ntrs.nasa.gov/citations/20230003916','use':'Published in-flight mean 7.33h, SD 1.16h for sample (n=19; 2137 nights), only a population-level check','direct_raw_data_fitted':'No'},
 {'source_id':'NASA-CO2','organization':'NASA OCHMO','title':'OCHMO-TB-004 Carbon Dioxide','url':'https://www.nasa.gov/ochmo-tb-004-carbon-dioxide-2/','use':'NASA-reported cabin CO2 monitoring framework, exposure standards and uncertainty of headache association; no probability fit','direct_raw_data_fitted':'No'},
 {'source_id':'NASA-STDM','organization':'NASA HRP','title':'Spaceflight Standard Measures','url':'https://www.nasa.gov/directorates/smd/space-life-physical-sciences-research-applications-division/human-research-program/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space/','use':'Instrument, check-in and observation-category selection; not numeric distributions','direct_raw_data_fitted':'No'},
 {'source_id':'CDC-NHANES','organization':'CDC/NCHS','title':'NHANES 2017-2018 BPX_J blood pressure and pulse metadata','url':'https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BPX_J.htm','use':'Terrestrial measurement definitions/protocol and observed ranges; public XPT rows were not downloaded and model not statistically fit to NHANES','direct_raw_data_fitted':'No'},
]
write_csv('scientific_sources.csv',source_rows,list(source_rows[0]))

metric_rows=[dict(metric=m,unit=u,description=desc,provenance='SYNTHETIC',measurement_cadence=('hourly' if m.startswith('cabin') else 'intermittent_or_daily'),is_nasa_measured='NO') for m,(u,desc) in METRICS.items()]
write_csv('metric_dictionary.csv',metric_rows,list(metric_rows[0]))

truth=[
 {'event_id':'E001','day_start':56,'day_end':56,'scope':'cabin','event':'CABIN_SENSOR_MISSING','detail':'Multi-hour telemetry gap; test missingness, no inferred normal value','engineered_for_demonstration':True},
 {'event_id':'E002','day_start':61,'day_end':63,'scope':'cabin','event':'CO2_EXCURSION','detail':'CO2 deliberately rises for demonstration; cross-crew headache observations recorded, causal relation not established','engineered_for_demonstration':True},
 {'event_id':'E003','day_start':62,'day_end':63,'scope':'crew','event':'HEADACHE_REPORT_CLUSTER','detail':'AST-001 and AST-003 opted in to shared symptom context during the cabin CO2 excursion','engineered_for_demonstration':True},
 {'event_id':'E004','day_start':67,'day_end':69,'scope':'crew','event':'WEARABLE_GAP','detail':'AST-004 resting HR wearable data missing','engineered_for_demonstration':True},
 {'event_id':'E005','day_start':73,'day_end':79,'scope':'crew','event':'SLEEP_DISRUPTION','detail':'AST-002 synthetic short sleep with fatigue and mild HR shift; not a clinical condition','engineered_for_demonstration':True},
 {'event_id':'E006','day_start':50,'day_end':61,'scope':'crew','event':'TRANSIENT_HR_TREND','detail':'AST-004 small smooth HR change; exercise/rest contexts remain separate','engineered_for_demonstration':True},
]
write_csv('EVALUATION_ONLY_scenario_truth_NOT_FOR_LIVE_APP.csv',truth,list(truth[0]))

# Reference limits and assumptions: documented as synthetic, not NASA physiological standards.
parameters={
 'generator_version':'1.0.0','seed':SEED,'dataset_id':MISSION_ID,'mission_type':'FICTIONAL_90_DAY_TRANSIT','days':DAYS,'crew_count':len(PROFILES),
 'historical_days':REPLAY_START,'replay_days':DAYS-REPLAY_START,'mission_start_utc':ts(1),
 'all_records_are_synthetic':True,'no_real_astronaut_medical_records':True,
 'sleep_nasa_reference':{'mean_inflight_h':7.33,'sd_inflight_h':1.16,'comparison_only':True},
 'co2_reference':{'cabin_one_hour_average_limit_mmhg':3.0,'note':'NASA OCHMO reference; not applied here as autonomous clinical severity rule'},
 'cabin_total_pressure_assumed_mmhg':ATM_PRESSURE_MMHG,
 'parameter_note':'Terrestrial pulse/BP profiles, day-to-day distributions and correlation coefficients are illustrative chosen model parameters, not fitted to raw NHANES or astronaut individual data. NASA sleep aggregate and CO2 guidance are external checks, not a validated simulation. CO2 is correlated with demo symptoms by construction, not causal proof.',
 'replay_policy':{'start_day':REPLAY_START,'historical_file':'replay_history_DAY01_to_DAY45.csv','hidden_future_file':'replay_future_HIDDEN_DAY46_to_DAY90.csv','rule':'Models and UI must only see observations at or before current simulated clock; evaluation event labels NEVER supplied to live app'},
 'observation_quality_values':['VALID','MISSING'],'provenance_values':['SYNTHETIC'],
 'references':source_rows
}
(HERE/'dataset_manifest.json').write_text(json.dumps(parameters,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

# Report verifies invariants with exact counts, and does not overclaim clinical validity.
qualities=Counter(x['quality'] for x in obs)
metric_counts=Counter(x['metric'] for x in obs)
assert len(PROFILES)==4 and len(summary)==360
assert len(history)+len(future)==len(obs)
assert len({r['observation_id'] for r in obs})==len(obs)
assert all(r['value']=='' for r in obs if r['quality']=='MISSING')
assert all(r['mission_day']<=REPLAY_START for r in history)
assert all(r['mission_day']>REPLAY_START for r in future)
assert all(float(r['value'])>=0 for r in obs if r['quality']=='VALID' and r['metric']!='cabin_temperature')
for c in [p['crew_id'] for p in PROFILES]:
  for d in range(1,DAYS+1):
    a=val(c,d,'systolic_bp');b=val(c,d,'diastolic_bp')
    if a or b:assert a and b and float(a)>float(b)

sleepvals=[float(r['value']) for r in health if r['metric']=='sleep_duration' and r['quality']=='VALID']
ppco2vals=[float(r['value']) for r in cabin if r['metric']=='cabin_co2_partial_pressure' and r['quality']=='VALID']
report={
 'record_total':len(obs),'health_records':len(health),'environment_records':len(cabin),
 'history_records':len(history),'future_replay_records':len(future),
 'crew_daily_summary_rows':len(summary),'mission_days':DAYS,'crew_count':len(PROFILES),
 'quality_counts':dict(qualities),'metric_counts':dict(sorted(metric_counts.items())),
 'sleep_mean_h':round2(statistics.mean(sleepvals)),'sleep_sd_h':round2(statistics.stdev(sleepvals)),
 'co2_max_mmhg':round2(max(ppco2vals)),'co2_max_ppm_at_assumed_pressure':round(max(ppco2vals)/760*1_000_000),
 'qa_checks_passed':['unique_observation_ids','consistent_90_day_split','no_future_records_in_history','missing_values_are_blank','valid_blood_pressure_pairs','exact_four_crew','exact_360_daily_summary_rows'],
 'limitations':['Not directly fit to NHANES public microdata; published CDC metadata only','No actual astronaut records included','Symptoms and CO2 test event co-occur by design; no causal evidence','Synthetic data cannot prove clinical accuracy','Future records included separately and must be kept hidden until replay','No validated population risk rates or diagnostic labels'],
}
(HERE/'validation_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')

readme='''# ASTRA v1 — Evidence-informed 90-day synthetic crew health dataset

**ALL RECORDS ARE SYNTHETIC.** Nothing here is a real NASA astronaut's medical record. This package is designed for software demonstration, replay, charting, provenance, missing-data handling, and rule-engine testing—not for medical diagnosis, astronaut physiology validation, or claims of diagnostic sensitivity/specificity.

## What is included

- Four fictional crew profiles matching the ASTRA demo crew, observed over 90 fictional in-flight days, January 1–March 30, 2040 (UTC).
- Long-format health observations: resting/exercise/recovery HR, sleep, optional symptom and mood check-ins, intermittent cuff BP, temperature and SpO2.
- Hourly cabin measurements: CO2 partial pressure, CO2 ppm, temperature, relative humidity; realistic temporal noise and occasional sensor gaps.
- A 45-day historical calibration/replay starting state and 45-day future-record file, both split by original timestamps.
- Deterministic generator code, explicit model/assumption manifest, scientific-source table, metric dictionary, and validation report.
- An **EVALUATION_ONLY** scenario file documenting engineered edge cases; **never expose this file to the algorithm during live replay**.

## Scientific basis & candid limitations

Research-informed anchors:
1. NASA Spaceflight Standard Measures lists actigraphy, sleep and mood questionnaires, and cardiovascular observations. This informs *which indicators are collected*, not numerical distributions.
2. Published NASA astronaut sleep study (19 crewmembers / 2,137 inflight nights): 7.33 ± 1.16 h across that sample. The simulated sleep distribution is loosely checked against this aggregate, not fit to astronaut individual records.
3. NASA OCHMO CO2 technical brief covers cabin partial-pressure monitoring and a one-hour average 3 mmHg reference limit. It does **not** establish that any simulated headache is caused by CO2.
4. CDC/NHANES BPX_J public metadata documents real human pulse/BP variables and measurement procedures. The downloadable individual-level data were **not** acquired here; pulse/BP model parameters are illustrative and **not** fit to NHANES distributions. The model should be recalibrated against a suitable large terrestrial sample for greater empirical fidelity.

This prototype models plausible-looking observations, not a validated statistical representation of long-duration astronaut physiology. Four synthetic crew profiles, correlation sizes, circadian effects and engineered scenarios are generator choices.

## Main files

- `crew_profiles.csv`: four fictional subject profiles.
- `health_observations.csv`: person-level long-form records.
- `cabin_environment_observations.csv`: cabin-level records.
- `all_observations_FULL_ARCHIVE.csv`: all records, including unrevealed future data; do not load this into runtime before replay completes.
- `replay_history_DAY01_to_DAY45.csv`: ingest at replay initialization.
- `replay_future_HIDDEN_DAY46_to_DAY90.csv`: held-back observations for the replay component to reveal by timestamp.
- `crew_daily_summary_FOR_REVIEW.csv`: 360 daily rows for inspection and Excel-friendly review; not a replacement for timestamped raw observations.
- `metric_dictionary.csv`: units, definitions, and intended sampling cadence.
- `scientific_sources.csv`: exact external source URLs and truthful calibration usage.
- `dataset_manifest.json`: model decisions and replay policy.
- `EVALUATION_ONLY_scenario_truth_NOT_FOR_LIVE_APP.csv`: scenario-generation truth labels; don't hand to production assessment logic or ML as ground-truth diseases.
- `validation_report.json`: structural QA and descriptive statistics.
- `generate_dataset.py`: deterministic generator, with NumPy dependency.

## Schema and ASTRA integration

The long-form observation schema deliberately resembles ASTRA's concepts (subject/mission, timestamp, metric, unit, activity context, provenance, quality and consent), but **is not guaranteed to match the actual current FastAPI POST schema**. Build a small adapter using the existing ASTRA contracts; do not replace service code or DB to force these CSVs to fit.

`provenance = SYNTHETIC` and `source = synthetic_*` must remain visible in imports and on dashboard/reports.

`privacy = private_health` means symptom/mood records must not be revealed across crew by default. `share_cabin_context = true` means an opt-in fictional symptom flag can contribute to aggregate cabin correlation, not full raw symptom detail sharing.

Do NOT use future observations, generator latent state, or evaluation-only event labels in training, baseline computation, feature engineering, medical alerts, or explanations during the historical replay. Reveal observations only when `timestamp_utc <= current_simulated_time`.

## Engineering scenario guide (NOT epidemiology)

- Days 1–45: historical records for baseline computation; individual variation and natural measurement gaps.
- Days 46–60: ordinary replay plus minor physiological drift and a 9-hour telemetry gap on Day 56.
- Days 61–63: synthetic elevated cabin CO2 and two opted-in headaches for a clear system test; no causal inference.
- Days 67–69: AST-004 wearable morning HR gap.
- Days 73–79: AST-002 synthetic sleep disruption and more fatigue.

Only the observations are available to ASTRA. This guide is for the evaluator/developer, not the live health-monitoring engine.

## Reproduce

```bash
python -m pip install numpy
python generate_dataset.py
```

Stable random seed: `20261114`. The files overwrite to identical generated values for this Python+NumPy-compatible generator version.

## Source citations

- NASA HRP Spaceflight Standard Measures: https://www.nasa.gov/directorates/smd/space-life-physical-sciences-research-applications-division/human-research-program/spaceflight-standard-measures-characterizing-how-humans-adapt-in-space/
- NASA astronaut sleep study: https://ntrs.nasa.gov/citations/20230003916
- NASA OCHMO CO2 brief: https://www.nasa.gov/ochmo-tb-004-carbon-dioxide-2/
- CDC/NHANES BPX_J codebook: https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/BPX_J.htm
'''
(HERE/'README.md').write_text(readme,encoding='utf-8')
print(json.dumps(report,indent=2))
