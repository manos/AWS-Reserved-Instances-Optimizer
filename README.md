# Note: not maintained any longer. See issues for what needs updating.

# rize.py

Script to analyze reserved instance utilization.

Currently: assumes 1-year heavy utilization reserved instances.

# Identifies:
* Reservations that aren't being used (and the total monthly cost/waste)
* Running instances that aren't reserved
* Cost savings if you were to reserve all running on-demand instances
* Time to recoup up-front reservation costs

JSON Data is downloaded automatically from www.cloudomix.com
and has support for all regions at time of writing

## Prerequisites
You'll need to install `boto` and `texttable`:
```
easy_install boto
easy_install texttable
```

Then configure `boto` with your AWS key:
```
cat <<EOF > ~/.boto
[Credentials]
aws_access_key_id = foo
aws_secret_access_key = bar
EOF
```

## Running:
Run with defaults:
```
./rize.py
```

Exclude instances with security group matching -e <regex>:
```
./rize.py -e '^ElasticMap.*'
```

Run in us-west-2:
```
./rize.py -r us-west-2
```

List all reserved instances and exit:
```
./rize.py -l
```

Operate only on VPC instances/reservations:
```
./rize.py --vpc
```
