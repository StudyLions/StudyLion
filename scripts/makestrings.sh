#!/bin/bash

for filename in locales/domains/*.txt; do
  domain=$(basename "$filename" .txt)
  echo "Creating template for domain: $domain"
  xgettext -f $filename -o locales/templates/$domain.pot --keyword=_p:1c,2 --keyword=_n:1,2 --keyword=_np:1c,2,3 -c --debug --from-code=utf-8
done
