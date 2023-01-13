#!/bin/bash
echo "======================================================" >> $ResultLog
echo "DNSFilter Debugger for Mac"
echo "The purpose of this tool is to assist support engineers with common requests."
#CREATED BY RICK COHEN DEC 2022
echo "======================================================" >> $ResultLog
# Create the "DNSFilter Logs" directory if it doesn't exist
if [ ! -d "$HOME/Downloads/DNSFilterLogs" ]; then
  mkdir $HOME/Downloads/DNSFilterLogs
fi

# Store all results to this file
LogFolder=$HOME/Downloads/DNSFilterLogs
ResultLog=$HOME/Downloads/DNSFilterLogs/DNSFilterDebug.txt

# Verify the script is ran as sudo user
if [ "$EUID" -ne 0 ]; then 
  echo "Please run as root"
  exit
fi
echo "======================================================" >> $ResultLog

echo "Checking to see if 'DNSFilter Agent' is active..."
echo "======================================================"
if (sudo launchctl list | grep -q "com.dnsfilter.agent.macos.helper"); then
  echo "DNSFilter Agent is active" >> $ResultLog
else
  echo "DNSFilter Agent is not active" >> $ResultLog
fi

echo "======================================================" >> $ResultLog

# Check to see if "DNS Agent" is active
echo "Checking to see if 'DNS Agent' is active..."
if (sudo launchctl list | grep -q "io.netalerts.agent.macos.helper"); then
  echo "DNS Agent is active" >> $ResultLog
else 
  echo "DNS Agent is not active" >> $ResultLog
fi

echo "======================================================" >> $ResultLog
# Perform a ping for 4 attempts to 8.8.8.8
echo "Performing ping"
ping -c 4 8.8.8.8
ping -c 4 8.8.8.8 >> $ResultLog

echo "======================================================" >> $ResultLog

# Perform nslookup -type=txt debug.dnsfilter.com
echo "Performing first nslookup"
nslookup -type=txt debug.dnsfilter.com
nslookup -type=txt debug.dnsfilter.com >> $ResultLog

echo "======================================================" >> $ResultLog

# Perform nslookup -type=txt debug.dnsfilter.com 103.247.36.36
echo "Performing second nslookup"
nslookup -type=txt debug.dnsfilter.com 103.247.36.36
nslookup -type=txt debug.dnsfilter.com 103.247.36.36 >> $ResultLog

echo "======================================================" >> $ResultLog

# Perform nslookup -type=txt debug.dnsfilter.com 103.247.37.37
echo "Performing final nslookup"
nslookup -type=txt debug.dnsfilter.com 103.247.37.37
nslookup -type=txt debug.dnsfilter.com 103.247.37.37 >> $ResultLog


echo "======================================================" >> $ResultLog
echo "======================================================" 
echo "======================================================" 
# Gather Agent Logs from roaming client and move them to $HOME/Downloads/DNSFilterLogs
sudo cp /var/log/com.dnsfilter.agent.macos.helper/daemon.log $HOME/Downloads/DNSFilterLogs
sudo cp /var/log/io.netalerts.agent.macos.helper/daemon.log $HOME/Downloads/DNSFilterLogs
echo "Agent Logs Copied"
echo "Agent Logs Copied to DNSFilterLogs folder" >> $ResultLog
echo "======================================================" >> $ResultLog


#Check for port 53 bindings
echo "Checking for any issues with localhost:53"
echo "The follow PID and Applications are using port 53" >> $ResultLog
lsof -i :53 | awk '{print $2, $1}' >> $ResultLog
echo "==============================================" >> $ResultLog


echo "======================================================" 
echo "======================================================" 
echo "The script has finished and the results are found in $ResultLog, please attach back to your support engineer"
echo "======================================================"
echo "======================================================" 