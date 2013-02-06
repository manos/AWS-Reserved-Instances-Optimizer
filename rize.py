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
# only cares about heavy-utilization 1-year reserved instances.
#
# Requires: ~/.boto, boto lib, texttable lib
#
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
parser.add_option("-d", "--debug", default=None, action="store_true",
                  help="enable debug output")
parser.add_option("-l", "--list", default=None, action="store_true",
                  help="list all reservations and exit")
parser.add_option("-e", "--exclude", metavar="regex", default='__None__',
                  help="exclude instances by security group name. takes regex")
parser.add_option(
    "-r", "--region", default='us-east-1', help="ec2 region to connect to")
(options, args) = parser.parse_args()

# set up logging
if options.debug:
    log_level = logging.DEBUG
else:
    log_level = logging.INFO

logging.basicConfig(stream=sys.stdout, level=log_level)
logging.basicConfig(stream=sys.stderr, level=(logging.ERROR, logging.CRITICAL))

rates = {'us-east-1': {'m1.small': {'hourly': .06, 'hu-1y': (195, .016)},
                       'm1.medium': {'hourly': .12, 'hu-1y': (390, .032)},
                       'm1.large': {'hourly': .24, 'hu-1y': (780, .064)},
                       'm1.xlarge': {'hourly': .48, 'hu-1y': (1560, .128)},
                       'm3.xlarge': {'hourly': .50, 'hu-1y': (1716, .141)},
                       'm3.2xlarge': {'hourly': 1.00, 'hu-1y': (3432, .282)},
                       't1.micro': {'hourly': .02, 'hu-1y': (62, .005)},
                       'm2.xlarge': {'hourly': .41, 'hu-1y': (1030, .088)},
                       'm2.2xlarge': {'hourly': .82, 'hu-1y': (2060, .176)},
                       'm2.4xlarge': {'hourly': 1.64, 'hu-1y': (4120, .352)},
                       'c1.medium': {'hourly': .145, 'hu-1y': (500, .04)},
                       'c1.xlarge': {'hourly': .58, 'hu-1y': (2000, .16)},
                       'cc1.4xlarge': {'hourly': 1.30, 'hu-1y': (4060, .297)},
                       'cc2.8xlarge': {'hourly': 2.40, 'hu-1y': (5000, .361)},
                       'cg1.4xlarge': {'hourly': 2.10, 'hu-1y': (6830, .494)},

                       },
         'us-west-2': {'m1.small': {'hourly': .06, 'hu-1y': (195, .016)},
                       'm1.medium': {'hourly': .12, 'hu-1y': (390, .032)},
                       'm1.large': {'hourly': .24, 'hu-1y': (780, .064)},
                       'm1.xlarge': {'hourly': .48, 'hu-1y': (1560, .128)},
                       'm3.xlarge': {'hourly': .50, 'hu-1y': (1716, .141)},
                       'm3.2xlarge': {'hourly': 1.00, 'hu-1y': (3432, .282)},
                       't1.micro': {'hourly': .02, 'hu-1y': (62, .005)},
                       'm2.xlarge': {'hourly': .41, 'hu-1y': (1030, .088)},
                       'm2.2xlarge': {'hourly': .82, 'hu-1y': (2060, .176)},
                       'm2.4xlarge': {'hourly': 1.64, 'hu-1y': (4120, .352)},
                       'c1.medium': {'hourly': .145, 'hu-1y': (500, .04)},
                       'c1.xlarge': {'hourly': .58, 'hu-1y': (2000, .16)},

                       },
         'eu-west-1': {'m1.small': {'hourly': .065, 'hu-1y': (195, .025)},
                       'm1.medium': {'hourly': .13, 'hu-1y': (390, .05)},
                       'm1.large': {'hourly': .26, 'hu-1y': (780, .10)},
                       'm1.xlarge': {'hourly': .52, 'hu-1y': (1560, .20)},
                       'm3.xlarge': {'hourly': .55, 'hu-1y': (1716, .141)},
                       'm3.2xlarge': {'hourly': 1.10, 'hu-1y': (3432, .282)},
                       't1.micro': {'hourly': .02, 'hu-1y': (62, .008)},
                       'm2.xlarge': {'hourly': .46, 'hu-1y': (1030, .148)},
                       'm2.2xlarge': {'hourly': .92, 'hu-1y': (2060, .296)},
                       'm2.4xlarge': {'hourly': 1.84, 'hu-1y': (4120, .592)},
                       'c1.medium': {'hourly': .165, 'hu-1y': (500, .063)},
                       'c1.xlarge': {'hourly': .66, 'hu-1y': (2000, .25)},
                       },
         }


def costs(item):
    """ takes a tuple of properties, and returns:
        ((monthly, yearly), (monthly, yearly), upfront) cost
        of (ondemand, 1-yr-heavy-utilization-ri).. for one instance.
        imput: (instance_type, availability_zone)
    """
    instance, zone = item
    monthly_ondemand = float(
        730 * float(rates[options.region][instance]['hourly']))
    yearly_ondemand = 12 * monthly_ondemand

    monthly_ri = float(730
                       * float(rates[options.region][instance]['hu-1y'][1])
                       + float(rates[options.region][instance]['hu-1y'][0])
                       / 12)
    yearly_ri = 12 * monthly_ri

    upfront = float(rates[options.region][instance]['hu-1y'][0])

    return (('%.2f' % monthly_ondemand, '%.2f' % yearly_ondemand),
            ('%.2f' % monthly_ri, '%.2f' % yearly_ri), upfront)


def summarize_tuples(items):
    ''' takes a tuple of properties, and summarizes into a dict.
        input: (instance_type, availability_zone, instance_count) '''
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

    if "None" not in options.exclude:
        instances = [i for r in conn.get_all_instances()
                     for i in r.instances
                     if not re.match(options.exclude, r.groups[0].name)]
    else:
        instances = [i for r in conn.get_all_instances() for i in r.instances]

    active_reservations = [i for i in conn.get_all_reserved_instances()
                           if 'active' in i.state
                           or 'payment-pending' in i.state]

    all_res = [(res.instance_type, res.availability_zone,
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
            waste = float(costs((res.instance_type, res.instance_count))[
                          1][0]) * (res.instance_count - running)
            total_waste += waste

            print "ERR: only %i running %s instances in %s, but %s are " \
                  "reserved! Monthly waste: " \
                  "%s" % (running, res.instance_type,
                          res.availability_zone, res.instance_count,
                          locale.currency(waste, grouping=True))

    if total_waste > 0:
        print "\nTotal monthly waste: %s\n" % locale.currency(total_waste,
                                                              grouping=True)

    ''' identify non-reserved running instances '''

    all_instances = [(ins.instance_type, ins.placement, 1)
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
    table.set_cols_dtype(['t', 't', 't', 't', 't', 't', 't', 't'])
    table.set_cols_align(["l", "c", "c", "c", "r", "r", "r", "r"])
    table.add_row(
        ["instance type", "zone", "# running", "# reserved", "monthly savings",
         "yearly savings", "current monthly", "only_RIs monthly"])

    for i in sorted(ins_dict):
        # dict i is: {(inst_type, az): count}

        # find # of reserved instances, and # on-demand:
        if i[0] in res_dict:
            res_count = int(res_dict[i[0]])
        else:
            res_count = 0

        run_count = int(i[1])

        inst_type, az = i[0]

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
            [inst_type, az, run_count, res_count,
             locale.currency(monthly, grouping=True),
             locale.currency(yearly, grouping=True),
             locale.currency(cur_monthly, grouping=True),
             locale.currency(all_ri_monthly, grouping=True),
             ])

    table.add_row(['Totals:', '', '', '', '', '', '', '', ])
    table.add_row(
        [' ', ' ', total_instances, res_instances,
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
