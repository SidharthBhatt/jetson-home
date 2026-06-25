#!/bin/bash
apt-get update
apt-get install -y curl
# set -e
export LC_ALL=C.UTF-8
export LANG=C.UTF-8


IFS=', ' read -r -a array <<< "$ENDPOINTS"

for endpoint in "${array[@]}"
do  
   until [ "$(curl -s -w '%{http_code}' -o /dev/null "http://localhost:$endpoint")" -eq 200 ]; do echo "Waiting for service endpoint to be up"; sleep 2; done;
done

echo "All healthcheck passed..."
exit 0
