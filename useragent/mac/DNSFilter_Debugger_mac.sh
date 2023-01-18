#!/bin/bash

# Store all results to this file
ResultLog=$HOME/Downloads/DNSFilterLogs/DNSFilterDebug.txt
echo "" > $ResultLog

echo "======================================================" 
echo "DNSFilter Debugger for Mac"
echo "The purpose of this tool is to assist support engineers with common requests."
#CREATED BY RICK COHEN DEC 2022
echo "======================================================" 
# Create the "DNSFilter Logs" directory if it doesn't exist
if [ ! -d "$HOME/Downloads/DNSFilterLogs" ]; then
  mkdir -p $HOME/Downloads/DNSFilterLogs
fi

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
echo " " >>$ResultLog
# List Info for active network adapters
echo "Active Network Adapters:" >> $ResultLog
echo "------------------------" >> $ResultLog

for interface in $(ifconfig -l); do
    ip=$(ifconfig $interface | awk '/inet /{print $2}')
    if [ -n "$ip" ]; then
        echo "Adapter: $interface" >> $ResultLog
        mac=$(ifconfig $interface | awk '/ether /{print $2}')
        subnet_hex="$(ifconfig | grep "netmask " | grep -v 0xff0 | sed -e 's/.*0x\(.*\)broadcast.*/\1/')"
        subnet_dec=$((16#${subnet_hex}))
        subnet_ip=$(printf "%d.%d.%d.%d\n" $((${subnet_dec} >> 24 & 255)) $((${subnet_dec} >> 16 & 255)) $((${subnet_dec} >> 8 & 255)) $((${subnet_dec} & 255)))
        router=$(netstat -nr | grep -v "::" | grep default | awk '{print $2}')
        dns=$(scutil --dns | grep nameserver | awk '{print $3}')
        echo "IP address: $ip" >> $ResultLog
        echo "Subnet Mask: $subnet_ip" >> $ResultLog
        echo "MAC address: $mac" >> $ResultLog
        echo "Router: $router" >> $ResultLog
        echo "DNS Servers: $dns" >> $ResultLog
        echo  "  ">> $ResultLog
    fi
done

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
echo "The script is completed and the results are found in $ResultLog, please attach to your support ticket"
open $HOME/Downloads/DNSFilterLogs
echo "======================================================"
echo "======================================================" 