#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

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
# only cares about heavy-utilization 1-year reserved instances.
#
# TODO: I'm formatting currency based on locale, but doesn't AWS always
# charge in $USD?
#
# Requires: ~/.boto, boto lib, texttable lib
#
#
import sys
import os
import re
import math
import logging
import boto.ec2
import locale
import texttable
import json
import urllib2
from optparse import OptionParser

locale.setlocale(locale.LC_ALL, '')

parser = OptionParser("usage: %prog [options]")
parser.add_option("-d", "--debug", default=None, action="store_true",
                  help="enable debug output")
parser.add_option("-l", "--list", default=None, action="store_true",
                  help="list all reservations and exit")
parser.add_option("-p", "--print-monthly", default=None, action="store_true",
                  help="list all reservations instances' monthly cost (1-yr ri)")
parser.add_option("-e", "--exclude", metavar="regex", default='__None__',
                  help="exclude instances by security group name. takes regex")
parser.add_option("-r", "--region", default='us-east-1',
                  help="ec2 region to connect to")
parser.add_option("--vpc", default=False, action="store_true",
                  help="operate on VPC instances/reservations only")
parser.add_option("-j", "--json", default='ec2.json',
                  help="json price file to read in or write to")
(options, args) = parser.parse_args()

# set up logging
if options.debug:
    log_level = logging.DEBUG
else:
    log_level = logging.INFO

logging.basicConfig(stream=sys.stdout, level=log_level)
logging.basicConfig(stream=sys.stderr, level=(logging.ERROR, logging.CRITICAL))

# Download the API Data file if it doesn't exist already
if not os.path.isfile(options.json):
    # Pull down price file
    logging.info("Downloading price file to %s" % options.json)
    pricefile = urllib2.urlopen('http://www.cloudomix.com/json/ec2.json')
    output = open(options.json,'wb')
    output.write(pricefile.read())
    output.close()

try:
    with open(options.json):
        json_data = open(options.json)
        rates = json.load(json_data)

except IOError as e:
    logging.error("Cannot open JSON file %s: %s" % (options.json, e))

def get_friendly_platform(p):
    """ Get a common friendly platform name to
        use. This name matches the one we
        get from the www.cloudomix.com JSON file """

    # Parse provided values from ec2
    if p == None:
        new_platform = 'linux'
    elif p == 'windows':
        new_platform =  'mswin'
    # Also cover RI descriptions for matching
    elif p == 'Linux/UNIX' or p == 'Linux/UNIX (Amazon VPC)':
        new_platform = 'linux'
    elif p == 'Windows' or p == 'Windows (Amazon VPC)':
        new_platform = 'mswin'
    else:
        logging.error('Unknown platform provided')
        sys.exit()
    return new_platform

def costs(item):
    """ takes a tuple of properties, and returns:
        ((monthly, yearly), (monthly, yearly), upfront) cost
        of (ondemand, 1-yr-heavy-utilization-ri).. for one instance.
        input: (instance_type, platform, region)
    """
    instance_type, platform, zone = item
    try:
        instance_ondemand = rates[platform][options.region][instance_type]['default']['on-demand'][1:]
    except KeyError as e:
        logging.error("KeyError: %s" % e)
    upfront = float(rates[platform][options.region][instance_type]['default']['ri-heavy-yrTerm1'][1:])
    instance_ri_hourly = rates[platform][options.region][instance_type]['default']['ri-heavy-yrTerm1Hourly'][1:]
    monthly_ondemand = float(
        730 * float(instance_ondemand))
    yearly_ondemand = 12 * monthly_ondemand

    monthly_ri = float(730
                       * float(instance_ri_hourly)
                       + float(upfront)
                       / 12)
    yearly_ri = 12 * monthly_ri


    return (('%.2f' % monthly_ondemand, '%.2f' % yearly_ondemand),
            ('%.2f' % monthly_ri, '%.2f' % yearly_ri), upfront)


def summarize_tuples(items):
    ''' takes a tuple of properties, and summarizes into a dict.
        input: (instance_type, availability_zone, instance_count) '''
    result = {}
    for res in items:
        key = (res[0], res[1], res[2])
        if key not in result:
            result.update({key: res[3]})
        else:
            result[key] += res[3]
    return result

if __name__ == '__main__':
    # TODO: security group based filtering doesn't work on VPC instances.
    if "None" not in options.exclude and options.vpc:
        logging.error("Sorry, you can't currently exclude by security group "
                      "regex with VPC enabled.")
        sys.exit(1)

    ''' just print monthly prices, if -p was used '''
    if options.print_monthly:
        omitted = []
        print "Current monthly pricing (1-year reserved) per instance type:"
        for instance_type in rates['linux'][options.region]:
            try:
                ri_hourly = float(rates['linux'][options.region][instance_type]['default']['ri-heavy-yrTerm1Hourly'][1:])
                print "%s\t%s" % (instance_type, ri_hourly)
            except (KeyError, ValueError):
                logging.debug("Error parsing price for %s" % instance_type)
                omitted.append(instance_type)

        if omitted:
            logging.debug("These instances omitted due to non-integer values: %s" % (', '.join(omitted)))

        sys.exit(0)

    conn = boto.ec2.connect_to_region(options.region)

    # not filtering by security group? it'll break with vpc instances that
    # don't have a 'name' attribute, so don't even try:
    if "None" not in options.exclude:
        instances = [i for r in conn.get_all_instances()
                     for i in r.instances
                     if len(r.groups) > 0 and not re.match(options.exclude, r.groups[0].name)]
    else:
        instances = [i for r in conn.get_all_instances() for i in r.instances]

    active_reservations = [i for i in conn.get_all_reserved_instances()
                           if 'active' in i.state
                           or 'payment-pending' in i.state]

    # re-set list of instances and reservations to only VPC ones, if --vpc
    # otherwise, exclude VPC instances/reservations. *hacky*
    if options.vpc:
        active_reservations = [res for res in active_reservations
                               if "VPC" in res.description]
        instances = [inst for inst in instances if inst.vpc_id]
    else:
        active_reservations = [res for res in active_reservations
                               if "VPC" not in res.description]
        instances = [inst for inst in instances if inst.vpc_id is None]

    # no instances were found, just bail:
    if len(instances) == 0:
        logging.error("Sorry, you don't seem to have any instances "
                      "here. Nothing to do. (try --vpc?)")
        sys.exit(1)

    all_res = [(res.instance_type, get_friendly_platform(res.description), res.availability_zone,
                res.instance_count) for res in active_reservations]
    res_dict = summarize_tuples(all_res)

    ''' just print reservations, if -l is used '''
    if options.list:
        print "Current active reservations:\n"
        for i in sorted(res_dict.iteritems()):
            print i[0][0], i[0][1], i[1]
        sys.exit(0)

    ''' find cases where we're running fewer instances than we've reserved '''
    total_waste = 0
    for res in active_reservations:
        matches = [
            i for i in instances if res.availability_zone in i.placement]
        running = len(
            [i.instance_type for i in matches
                if i.instance_type in res.instance_type
                and "running" in i.state])

        if running < res.instance_count:
            waste = float(costs((res.instance_type, get_friendly_platform(res.description), res.instance_count))[
                          1][0]) * (res.instance_count - running)
            total_waste += waste

            print "ERR: only %i running %s instances in %s, but %s are " \
                  "reserved! Monthly waste: " \
                  "%s" % (running, res.instance_type,
                          res.availability_zone, res.instance_count,
                          locale.currency(waste, grouping=True).decode(locale.getpreferredencoding())
                          )

    if total_waste > 0:
        print "\nTotal monthly waste: %s\n" % locale.currency(total_waste,
                                                              grouping=True).decode(locale.getpreferredencoding())

    ''' identify non-reserved running instances '''

    all_instances = [(ins.instance_type, get_friendly_platform(ins.platform), ins.placement, 1)
                     for ins in instances if "running" in ins.state]
    ins_dict = summarize_tuples(all_instances).iteritems()

    print "\n== Summary of running instances and their reserved instances ==\n"

    yearly_savings = float(0)
    monthly_savings = float(0)
    upfront_cost = float(0)
    total_instances = 0
    res_instances = 0
    monthly_od_sum = 0
    monthly_ri_sum = 0

    table = texttable.Texttable(max_width=0)
    table.set_deco(texttable.Texttable.HEADER)
    table.set_cols_dtype(['t', 't', 't', 't', 't', 't', 't', 't', 't'])
    table.set_cols_align(["l", "l", "c", "c", "c", "r", "r", "r", "r"])
    table.add_row(
        ["instance type", "platform", "zone", "# running", "# reserved",
         "monthly savings", "yearly savings", "current monthly", "only_RIs monthly"])

    for i in sorted(ins_dict):
        # dict i is: {(inst_type, platform, az): count}

        # find # of reserved instances, and # on-demand:
        if i[0] in res_dict:
            res_count = int(res_dict[i[0]])
        else:
            res_count = 0

        run_count = int(i[1])

        inst_type, platform, az = i[0]

        od, ri, upfront = costs(tuple(i[0]))
        od_monthly, od_yearly = [float(x) for x in od]
        ri_monthly, ri_yearly = [float(x) for x in ri]

        # determine monthly savings, if we're running more than are reserved:
        od_count = int(run_count) - int(res_count)

        if od_count > 0:
            monthly = od_count * (od_monthly - ri_monthly)
            yearly = od_count * (od_yearly - ri_yearly)
            upfront_cur = float(upfront * od_count)
            cur_monthly = (od_count * od_monthly) + (res_count * ri_monthly)
            all_ri_monthly = (od_count + res_count) * ri_monthly
            cur_yearly = (od_count * od_yearly) + (res_count * ri_yearly)
            all_ri_yearly = (od_count + res_count) * ri_yearly
        else:
            monthly = 0
            yearly = 0
            upfront_cur = 0
            cur_monthly = (res_count * ri_monthly)
            all_ri_monthly = (res_count) * ri_monthly
            cur_yearly = (res_count * ri_yearly)
            all_ri_yearly = (res_count) * ri_yearly

        # totals
        yearly_savings += yearly
        monthly_savings += monthly
        upfront_cost += float(upfront_cur)
        monthly_od_sum += cur_monthly
        monthly_ri_sum += all_ri_monthly

        total_instances += int(run_count)
        res_instances += int(res_count)

        table.add_row(
            [inst_type, platform, az, run_count, res_count,
             locale.currency(monthly, grouping=True),
             locale.currency(yearly, grouping=True),
             locale.currency(cur_monthly, grouping=True),
             locale.currency(all_ri_monthly, grouping=True),
             ])

    table.add_row(['Totals:', '', '', '', '', '', '', '', '', ])
    table.add_row(
        [' ', ' ', ' ', total_instances, res_instances,
            locale.currency(monthly_savings, grouping=True),
            locale.currency(yearly_savings, grouping=True),
            locale.currency(monthly_od_sum, grouping=True),
            locale.currency(monthly_ri_sum, grouping=True),
         ])
    print table.draw()

    ''' more summaries '''

    print "\n== Savings Potential (reserve all on-demand instances) =="
    print "monthly: %s, yearly: %s\nupfront cost (already amortized in " \
          "'savings' calculations): %s" \
          "" % (locale.currency(monthly_savings, grouping=True),
                locale.currency(yearly_savings, grouping=True),
                locale.currency(upfront_cost, grouping=True),
                )

    print "\n== Current Costs (including waste; i.e. unused RIs) =="
    real_monthly = monthly_od_sum + total_waste
    real_yearly = real_monthly * 12

    print "Current total monthly expense: %s" % (
        locale.currency(real_monthly, grouping=True))
    print "Current total yearly expense: %s" % (
        locale.currency(real_yearly, grouping=True))

    """ Adding time-to-recover idea by Ozzie Sabina:
    https://github.com/osabina/AWS-Reserved-Instances-Optimizer/commit/fc8b466dcec057f1c9958ee418e1f655719ae31f
    ZeroDivisionError may happen, if all instances are reserved.
    """
    try:
        rf, rm = math.modf(upfront_cost
                           / (monthly_savings + (upfront_cost / 12)))
        rd = rf * 30
        print "Time to recover up-front cost: %s months, %s days.\n" % (
              int(rm), int(rd))
    except ZeroDivisionError:
        pass
