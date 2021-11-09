import json
import datetime
import matplotlib.pyplot as plt
import boto3
from dateutil import parser
from datetime import timedelta
from pprint import pprint
import math

TIMESTREAM_DB = '433-data'
S3_BUCKET = 'fsharp-433-data-graphs'


# API Endpoints:
# ==============
def one_day(event, context):
    return draw_graph('1d')

def three_day(event, context):
    return draw_graph('3d')

def sensor(event, context):
    return get_sensor_latest(event['pathParameters']['sensor'], event['pathParameters']['reading'])
# ==============

def get_sensor_latest(sensor, reading):
    timestream = boto3.client('timestream-query')
    
    if reading == 'dewpoint':
        tquery = f"SELECT * FROM \"{TIMESTREAM_DB}\".\"{sensor}\" \
                WHERE measure_name = 'temp' \
                ORDER BY time DESC LIMIT 1"
        hquery = f"SELECT * FROM \"{TIMESTREAM_DB}\".\"{sensor}\" \
                WHERE measure_name = 'humid' \
                ORDER BY time DESC LIMIT 1"
        tresponse = timestream.query(QueryString=tquery)
        hresponse = timestream.query(QueryString=hquery)

        temp = float(tresponse['Rows'][0]['Data'][3]['ScalarValue'])
        humid = float(hresponse['Rows'][0]['Data'][3]['ScalarValue'])
        A = 17.27
        B = 237.7
        alpha = ((A * temp) / (B + temp)) + math.log(humid/100.0)
        dewpoint = (B * alpha) / (A - alpha)

        return  {
            'time': tresponse['Rows'][0]['Data'][2]['ScalarValue'],
            'reading': round(dewpoint,1)
        }     

    query = f"SELECT * FROM \"{TIMESTREAM_DB}\".\"{sensor}\" \
              WHERE measure_name = '{reading}' \
              ORDER BY time DESC LIMIT 1"

    response = timestream.query(QueryString=query)

    return {
        'time': response['Rows'][0]['Data'][2]['ScalarValue'],
        'reading': float(response['Rows'][0]['Data'][3]['ScalarValue'])
    }

def draw_graph(time):
    data = fetch_data(time)
    if generate_graph(data):
        graph_url = upload_to_s3()

        body = {
            "url": graph_url
        }
    else:
        body = {
            "did": 'nothing'
        }

    response = {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Headers" : "Content-Type",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET"
        },
        "body": json.dumps(body)
    }

    return response

def fetch_data(timescale):
    return {
        'indoor': fetch_data_for_sensor('indoor', timescale),
        'outdoor': fetch_data_for_sensor('outdoor', timescale)
    }

def fetch_data_for_sensor(sensor, timescale):
    timestream = boto3.client('timestream-query')

    query = f"SELECT * FROM \"{TIMESTREAM_DB}\".\"{sensor}\" WHERE time > ago({timescale})"
    response = timestream.query(QueryString=query)

    print(f"Got {len(response['Rows'])} datapoints")

    humidities = []
    temperatures = []

    for row in response['Rows']:
        if row['Data'][1]['ScalarValue'] == 'humid':
            humidities.append({
                'time': parser.parse(row['Data'][2]['ScalarValue']) + timedelta(hours=1),
                'reading': float(row['Data'][3]['ScalarValue'])
            })
        elif row['Data'][1]['ScalarValue'] == 'temp':
            temperatures.append({
                'time': parser.parse(row['Data'][2]['ScalarValue']) + timedelta(hours=1),
                'reading': float(row['Data'][3]['ScalarValue'])
            })

    humidities = sorted(humidities, key=lambda item: item['time'])
    temperatures = sorted(temperatures, key=lambda item: item['time'])
    return {'humids': humidities, 'temps': temperatures}
    
def generate_graph(data):
    plt.style.use('dark_background')
    fig, axes = plt.subplots(2, sharex=True)

    draw_plot(fig, axes[0], data['indoor'])
    draw_plot(fig, axes[1], data['outdoor'])

    fig.tight_layout()
    fig.autofmt_xdate()

    plt.gcf().set_size_inches(15,9)
    plt.savefig('/tmp/output.png')
    return True

def draw_plot(fig, left_axis, data):
    red = '#FF6103'
    blue = '#4682B4'

    right_axis = left_axis.twinx()

    left_axis.set_xlabel('time')

    left_axis.set_ylabel('humidity', color=blue)
    right_axis.set_ylabel('temperature', color =red)

    left_axis.tick_params(axis='y', labelcolor=blue)
    right_axis.tick_params(axis='y', labelcolor=red)

    right_axis.grid(color=red, alpha=0.5, dashes=(3,9))
    left_axis.grid(color=blue, alpha=0.5, dashes=(3,12))
    
    left_axis.plot(
        [point['time'] for point in data['humids']],
        [point['reading'] for point in data['humids']],
        color=blue
    )
    right_axis.plot(
        [point['time'] for point in data['temps']],
        [point['reading'] for point in data['temps']],
        color=red
    )

def upload_to_s3():
    s3 = boto3.client('s3')
    s3.upload_file('/tmp/output.png', S3_BUCKET, 'output.png')
    s3.put_object_acl(ACL='public-read', Bucket=S3_BUCKET, Key='output.png')
    return f'https://{S3_BUCKET}.s3.amazonaws.com/output.png'

if __name__ == "__main__":
    three_day(None,None)
