# rize.py:

Script to analyze reserved instance utilization.
Currently: assumes 1-year heavy utilization reserved instances.

# Identifies:
* reservations that aren't being used (and the total monthly cost/waste)
* running instances that aren't reserved
* cost savings if you were to reserve all running on-demand instances
* time to recoup up-front reservation costs

Supported regions: us-east-1, us-west-1, us-west-2, eu-west-1.

Requires: ~/.boto, boto lib, texttable lib

## Running:
Run with defaults:
`./rize.py`

Exclude instances with security group matching -e <regex>:
`./rize.py -e '^ElasticMap.*'`

Run in us-west-2:
`./rize.py -r us-west-2`

List all reserved instances and exit:
`./rize.py -l`

Operate only on VPC instances/reservations:
`./rize.py --vpc`
