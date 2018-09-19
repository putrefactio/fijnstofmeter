import datetime
import math
import random
import sqlite3
import sys
import tweepy

# set a default period.
period = 'hour'

# number of measurements per period.
# The sensor takes a measurement every 150 seconds.
number_of_measurements = {
    'hour': 24,
    'day': 576
}

# see if we have an argument.
try:
    period = sys.argv[1]
except IndexError:
    pass

'''
https://www.rivm.nl/Onderwerpen/S/Smog/Waarschuwingsgrenzen_en_luchtkwaliteitsindex
UURGEMIDDELDE:

GOED:
    PM10:30
    PM25:20
MATIG:
    PM10:75
    PM25:50
ONVOLDOENDE:
    PM10:125
    PM25:90
SLECHT:
    PM10:200
    PM25:150
ZEER SLECHT:
    PM10:>200
    PM25:>150

DAGGEMIDDELDE:

GOED:
    PM10:15
MATIG:
    PM10:38
ONVOLDOENDE:
    PM10:70
SLECHT:
    PM10:100
ZEER SLECHT:
    PM10:>100
'''

verdict_terms = [
    'goed',
    'matig',
    'onvoldoende',
    'slecht',
    'zeer slecht'
]

# Map concentration value ranges to verdicts as stated by RIVM.
values = {
    'hour': {
        'PM10': {
            verdict_terms[0]: 30,
            verdict_terms[1]: 75,
            verdict_terms[2]: 125,
            verdict_terms[3]: 200
        },
        'PM25': {
            verdict_terms[0]: 20,
            verdict_terms[1]: 50,
            verdict_terms[2]: 90,
            verdict_terms[3]: 140
        }
    },
    'day': {
        'PM10': {
            verdict_terms[0]: 15,
            verdict_terms[1]: 38,
            verdict_terms[2]: 70,
            verdict_terms[3]: 100
        },
        'PM25': {
            verdict_terms[0]: 20,
            verdict_terms[1]: 50,
            verdict_terms[2]: 90,
            verdict_terms[3]: 150
        }
    }
}


# We need to compensate for relative humidity. RIVM gives us a few pointers.
def compensate_for_rh(measurement, rh):
    '''
    "De aldus gefitte vochtcorrectie geeft dan de factor waardoor de waarden
    van de sensoren moeten worden gedeeld."

    Correctie_Amersfoort = 3.4 * (100 – RH)^-0.40
    Correctie_Amsterdam = 2.3 * (100 – RH)^-0.38
    Correctie_Venlo = 3.9 * (100 – RH)^-0.43
    '''

    # Let's use the correction for Venlo, NL.
    correction = 3.9 * math.pow((100 - rh), -0.43)

    return measurement/correction


# calculate a mean measurement per hour or per day.
def calculate_mean(_period=24):
    conn = sqlite3.connect(
        # This needs to be the absolute path when run as
        # a cronjob!
        'measurements.db')
    c = conn.cursor()
    c.execute(
        "SELECT * FROM measurements ORDER BY datetime DESC LIMIT ?", [(
            _period)])
    rows = c.fetchall()
    conn.close()

    # Get the amount of time between now and the last measurement
    # in the dataset.
    delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(
        rows[-1][0])

    # No older than
    # 115% of `amount of measurements per period` * `measurement interval`
    stale_limit = round((_period * 150) * 1.15)

    # If the last measurement was more than the limit defined above, do
    # not send a tweet as it might be incorrect.
    # XXX This way of checking can be improved upon!
    if round(delta.total_seconds()) > stale_limit:
        sys.exit('Stale measurements, aborting.')

    means = {
        'PM10': 0,
        'PM25': 0
    }

    # now calculate means
    for row in rows:
        means['PM10'] += compensate_for_rh(row[1], row[3])
        means['PM25'] += compensate_for_rh(row[2], row[3])

    for key, total in means.items():
        means[key] = round(total / len(rows), 1)

    return means


means = calculate_mean(number_of_measurements[period])

verdict = {
    'PM10': None,
    'PM25': None
}


# compare means with our RIVM given range values and define a verdict.
def define_verdict(pm):
    _values = values[period][pm]
    if means[pm] < _values[verdict_terms[0]]:
        return verdict_terms[0]
    elif means[pm] > _values[verdict_terms[0]] and \
            means[pm] < _values[verdict_terms[1]]:
        return verdict_terms[1]
    elif means[pm] > _values[verdict_terms[1]] and \
            means[pm] < _values[verdict_terms[2]]:
        return verdict_terms[2]
    elif means[pm] > _values[verdict_terms[3]] and \
            means[pm] < _values[verdict_terms[4]]:
        return verdict_terms[3]
    else:
        return verdict_terms[4]


for key, item in verdict.items():
    verdict[key] = define_verdict(key)

# We want to comnplain when either PM10 or PM2,5 is too high.
# XXX This mechanism can be improved upon / symplified!
global_verdict = verdict_terms[
    max(
        verdict_terms.index(verdict['PM10']),
        verdict_terms.index(verdict['PM25']),
        )
    ]


# Construct the body of the tweet
def construct_tweet():
    # Let's be dramatic!
    exclamations = [
        'Oei! ',
        'Slecht nieuws! ',
        'Helaas! ',
        'Jammer! ',
        'O wee! ',
        'Hé bah! ',
        'Uche uche! ',
        'Oh nee! ',
        'Verdorie! ',
        'Gatsie! ',
        'Jakkes! ',
    ]
    # and pedantic!
    callouts = [
        ' Dit kan beter! ',
        ' Laten we er iets aan doen! ',
        ' Kies voor gezonde lucht! ',
        ' Dit maakt ons ziek! ',
        ' Hier moet iets aan gebeuren! ',
        ' Dit is te hoog! ',
        ' Hier zijn we niet blij mee! ',
    ]

    mentions = ('@rivm '
                '@gemeenteWveen '
                '@zuid_holland!')

    too_high = global_verdict != 'goed'

    body = {
        'hour': '{}Het afgelopen uur was de luchtkwaliteit mbt fijnstof '
                'in Waddinxveen Zuid \'{}\'. De uurgemiddelden luiden: PM2,5 '
                '{} µg/m³, PM10 {} µg/m³.{}{} #waddinxveen #fijnstof',
        'day': '{}De afgelopen dag was de luchtkwaliteit mbt fijnstof in '
                'Waddinxveen Zuid \'{}\'. De daggemiddelden luiden: PM2,5 '
                '{} µg/m³, PM10 {} µg/m³.{}{} #waddinxveen #fijnstof'
    }

    formatted = (body[period]).format(
        exclamations[random.randint(
            0, len(exclamations)-1)] if too_high else '',
        global_verdict,
        means['PM25'],
        means['PM10'],
        # Only do the pedantics and mentions when we are not 'goed'.
        callouts[random.randint(
            0, len(callouts)-1)] if too_high else '',
        mentions if too_high and period is not 'hour' else ''
    )

    return formatted


def send_tweet():
    consumer_key = 'twitter api consumer key'
    consumer_secret = 'twitter api consumer secret'
    access_token = 'twitter api access token'
    access_token_secret = 'twitter api token secret'

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)

    api = tweepy.API(auth)

    # Send tweet!
    api.update_status(construct_tweet())


# Don't tweet good news.
if global_verdict == 'goed' and period == 'hour':
    sys.exit('No need to tweet hourly good result, aborting.')

send_tweet()
