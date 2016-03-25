#!/bin/sh

# I do not know what this is as a process. I just wanted to get the data. This is how I fetched it.
#
# What language should this be in? Python? Javascript? Go? Forth? Whatever?
#
# ray@ganymede.org 2016/03/01
#
# If you do not have wget, curl or lynx, install them. I ran this on a Mac (OS X 10.11.3)

# By the way, I use lynx here because the -dump option make lynx non-interactive and it dumps out
# the web page, but more importantly it dumps out the URLs in the page in a very convenient list
# at the end. There are more modern ways to do this, of course, but this has always worked for me.

wget -r --no-parent 'http://www.sos.ca.gov/elections/prior-elections/statewide-election-results/'

if [ ! -d "pdfs_list.txt" ]; then

    find www.sos.ca.gov/ -type f -exec lynx \-dump {} \; | grep 'pdf$' | grep '^http' | \
        awk '{print substr($0,7)}' > pdfs_list.txt
fi

awk 'BEGIN{FS="/"}{print substr($0,8,length($0)-length($NF)-7)}' pdfs_list.txt | sort | uniq | \
    awk '{if ($0 != "") print "mkdir -p",$0}' | /bin/sh

awk 'BEGIN{FS="/"}{print "curl -s '\''"$0"'\'' > "substr($0,8)}' pdfs_list.txt | /bin/sh -vx

if [ ! -f "xls_list.txt" ]; then

    find www.sos.ca.gov/ -type f -exec lynx \-dump {} \; | grep '^ +[0-9]+\. ' | grep 'xls$' | \
        awk '{ if ($0 != "") print substr($0,7)}' > xls_list.txt
fi

awk 'BEGIN{FS="/"}{print substr($0,8,length($0)-length($NF)-7)}' xls_list.txt | sort | uniq | \
    awk '{if ($0 != "") print "mkdir -p",$0}' | /bin/sh

awk 'BEGIN{FS="/"}{print "curl -s '\''"$0"'\'' > "substr($0,8)}' xls_list.txt | /bin/sh -vx

if [ ! -d data ]; then

    mkdir -f data

fi

mv admin.cdn.sos.ca.gov/ elections.cdn.sos.ca.gov/ primary98.sos.ca.gov/ www.sos.ca.gov/ data/

# There are also MS Word files (.doc) referred to in the pages. If anyone wants them, more fool you
# but go ahead.

# And there you are, 1489 pdf files and 444 xls files.

