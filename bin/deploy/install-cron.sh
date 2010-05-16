#!/bin/sh
bin_dir=`dirname $0`/..
cron_dir=$bin_dir/../config/cron
copied_cron=/etc/cron.d/schemadb-push
#debug=echo
debug=
$debug cp $cron_dir/schemadb-push $copied_cron
$debug chown root.root $copied_cron
$debug chmod 0644 $copied_cron
echo "Next step: /etc/init.d/crond restart"
