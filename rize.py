#!/usr/bin/env python2.7
#
# @Author: "Charlie Schluting <charlie@schluting.com>"
# @Date:   June 2012
#
# Script to analyze reserved instance utilization.
#
# Identifies:
#   - reservations that aren't being used
#   - running instances that aren't reserved
#   - cost savings if you were to reserve all running on-demand instances
#
# TODO: how to handle light/medium utilization instances? This script assumes /
# only cares about full-time heavy-utilization instances.
#
# Requires: ~/.boto, boto lib, texttable lib
#
import sys
import os
import re
import logging
import boto.ec2
import locale
import texttable
from optparse import OptionParser

locale.setlocale(locale.LC_ALL, '')

parser = OptionParser("usage: %prog [options]")
parser.add_option("-d", "--debug", default=None, action="store_true", help="enable debug output")
parser.add_option("-l", "--list", default=None, action="store_true", help="list all reservations and exit")
parser.add_option("-e", "--exclude", metavar="regex", default=None, help="exclude a set of instances by security group name regex")
parser.add_option("-r", "--region", default='us-east-1', help="ec2 region to connect to")
(options, args) = parser.parse_args()

# set up logging
if options.debug: log_level = logging.DEBUG
else:             log_level = logging.INFO

logging.basicConfig(stream=sys.stdout, level=log_level)
logging.basicConfig(stream=sys.stderr, level=(logging.ERROR,logging.CRITICAL))

rates = { 'us-east-1': { 'm1.small':    { 'hourly': .08,  'hu-1y': (195, .016) },
                         'm1.medium':   { 'hourly': .16,  'hu-1y': (390, .032) },
                         'm1.large':    { 'hourly': .32,  'hu-1y': (780, .064) },
                         'm1.xlarge':   { 'hourly': .64,  'hu-1y': (1560, .128) },
                         't1.micro':    { 'hourly': .02,  'hu-1y': (62, .005) },
                         'm2.xlarge':   { 'hourly': .45,  'hu-1y': (1030, .088) },
                         'm2.2xlarge':  { 'hourly': .90,  'hu-1y': (2060, .176) },
                         'm2.4xlarge':  { 'hourly': 1.80, 'hu-1y': (4120, .352) },
                         'c1.medium':   { 'hourly': .165, 'hu-1y': (500, .04) },
                         'c1.xlarge':   { 'hourly': .66,  'hu-1y': (2000, .16) },
                         'cc1.4xlarge': { 'hourly': 1.30, 'hu-1y': (4060, .297) },
                         'cc2.8xlarge': { 'hourly': 2.40, 'hu-1y': (5000, .361) },
                         'cg1.4xlarge': { 'hourly': 2.10, 'hu-1y': (6830, .494) },

          },
          'us-west-2': { 'm1.small':    { 'hourly': .08,  'hu-1y': (195, .016) },
                         'm1.medium':   { 'hourly': .16,  'hu-1y': (390, .032) },
                         'm1.large':    { 'hourly': .32,  'hu-1y': (780, .064) },
                         'm1.xlarge':   { 'hourly': .64,  'hu-1y': (1560, .128) },
                         't1.micro':    { 'hourly': .02,  'hu-1y': (62, .005) },
                         'm2.xlarge':   { 'hourly': .45,  'hu-1y': (1030, .088) },
                         'm2.2xlarge':  { 'hourly': .90,  'hu-1y': (2060, .176) },
                         'm2.4xlarge':  { 'hourly': 1.80, 'hu-1y': (4120, .352) },
                         'c1.medium':   { 'hourly': .165, 'hu-1y': (500, .04) },
                         'c1.xlarge':   { 'hourly': .66,  'hu-1y': (2000, .16) },

          },
          'eu-west-1': { 'm1.small':    { 'hourly': .085, 'hu-1y': (195, .025) },
                         'm1.medium':   { 'hourly': .17,  'hu-1y': (390, .05) },
                         'm1.large':    { 'hourly': .34,  'hu-1y': (780, .10) },
                         'm1.xlarge':   { 'hourly': .68,  'hu-1y': (1560, .20) },
                         't1.micro':    { 'hourly': .02,  'hu-1y': (62, .008) },
                         'm2.xlarge':   { 'hourly': .506, 'hu-1y': (1030, .148) },
                         'm2.2xlarge':  { 'hourly': 1.012,'hu-1y': (2060, .296) },
                         'm2.4xlarge':  { 'hourly': 2.024,'hu-1y': (4120, .592) },
                         'c1.medium':   { 'hourly': .186, 'hu-1y': (500, .063) },
                         'c1.xlarge':   { 'hourly': .744, 'hu-1y': (2000, .25) },
          },
        }

def costs(item):
    ''' takes a tuple of properties, and returns ((monthly, yearly) (monthly, yearly)) cost
        of (ondemand, 1-yr-heavy-utilization-ri)
        imput: ((instance_type, availability_zone), instance_count) '''
    monthly_ondemand = item[1]*float(730*float(rates[options.region][item[0][0]]['hourly']))
    yearly_ondemand = 12*monthly_ondemand

    monthly_ri = item[1]*float(730*float(rates[options.region][item[0][0]]['hu-1y'][1]) + float(rates[options.region][item[0][0]]['hu-1y'][0])/12)
    yearly_ri = 12*monthly_ri

    return (('%.2f'%monthly_ondemand, '%.2f'%yearly_ondemand), ('%.2f'%monthly_ri, '%.2f'%yearly_ri))
def summarize_tuples(items):
    ''' takes a tuple of properties, and summarizes into a dict.
        imput: (instance_type, availability_zone, instance_count) '''
    result = {}
    for res in items:
        key = (res[0], res[1])
        if key not in result:
            result.update({key: res[2]})
        else:
            result[key] += res[2]
    return result

if __name__ == '__main__':
    conn = boto.ec2.connect_to_region(options.region)
    #instances = [i for r in conn.get_all_instances() for i in r.instances]
    instances = [i for r in conn.get_all_instances() for i in r.instances if 'Map' in r.groups[i].id ]

    print instances
    sys.exit(0)

    active_reservations = [i for i in conn.get_all_reserved_instances() if 'active' in i.state]

    all_res = [(res.instance_type, res.availability_zone, res.instance_count) for res in active_reservations]
    res_dict = summarize_tuples(all_res)

    ''' just print reservations, if -l is used '''
    if options.list:
        print "Current active reservations:\n"
        for i in sorted(res_dict.iteritems()):
            print i[0][0], i[0][1], i[1]
        sys.exit(0)

    ''' find cases where we're running fewer instances than we've reserved '''
    for res in active_reservations:
        matches = [i for i in instances if res.availability_zone in i.placement]
        running = len([i.instance_type for i in matches if i.instance_type in res.instance_type])
        if running < res.instance_count:
            print "ERR: only %i running %s instances in %s, but %i are reserved!" % (running, res.instance_type, res.availability_zone, res.instance_count)


    ''' identify non-reserved running instances '''
    all_instances = [(ins.instance_type, ins.placement, 1) for ins in instances if "running" in ins.state]
    ins_dict = summarize_tuples(all_instances).iteritems()
    print "\nSummary of running instances, and their reserved instances:\n"

    yearly_savings = float(0)
    monthly_savings = float(0)
    num_instances = 0
    res_instances = 0

    table = texttable.Texttable(max_width=0)
    table.set_deco(texttable.Texttable.HEADER)
    table.set_cols_dtype(['t', 't', 't', 't', 't', 't'])
    table.set_cols_align(["l", "c", "c", "c", "r", "r"])
    table.add_row(["instance type", "zone", "# running", "# reserved", "monthly savings", "yearly savings"])

    for i in sorted(ins_dict):
        if i[0] in res_dict: res_count = res_dict[i[0]]
        else: res_count = 0

        cost = costs(tuple(i))

        monthly = float(cost[0][0]) - float(cost[1][0])
        yearly = float(cost[0][1]) - float(cost[1][1])
        yearly_savings += yearly
        monthly_savings += monthly

        num_instances += int(i[1])
        res_instances += int(res_count)

        table.add_row([i[0][0], i[0][1], i[1], res_count, locale.currency(monthly, grouping=True), locale.currency(yearly, grouping=True)])

    print table.draw()
    print "\nTotals:"
    print "running on-demand instances: %i\nrunning reserved instances: %i\nsavings potential:\n\tmonthly: %s, yearly: %s" % (
        num_instances, res_instances, locale.currency(monthly_savings, grouping=True), locale.currency(yearly_savings, grouping=True))

