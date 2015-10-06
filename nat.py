#!/usr/bin/python

"""
Example to create a Mininet topology and connect it to the internet via NAT
through eth0 on the host.

Glen Gibb, February 2011

(slight modifications by BL, 5/13)
"""

from mininet.cli import CLI
from mininet.log import lg, info
from mininet.node import Node
from mininet.topolib import TreeNet
from mininet.util import quietRun

import ipaddress

#################################
def startNAT( root, inetIntf='eth0', intIP=None ):
    """Start NAT/forwarding between Mininet and external network
    root: node to access iptables from
    inetIntf: interface for internet access"""

    # Identify the interface connecting to the mininet network
    localIntf =  root.defaultIntf()
    root_ip = ipaddress.ip_interface(intIP)

    #root_ip = ipaddress.ip_interface(localIntf.IP())

    # Flush any currently active rules
    root.cmd( 'iptables -F' )
    root.cmd( 'iptables -t nat -F' )

    # Create default entries for unmatched traffic
    root.cmd( 'iptables -P INPUT ACCEPT' )
    root.cmd( 'iptables -P OUTPUT ACCEPT' )
    root.cmd( 'iptables -P FORWARD DROP' )

    # Configure NAT
    root.cmd( 'iptables -I FORWARD -i', localIntf, '-d', root_ip.network, '-j DROP' )
    root.cmd( 'iptables -A FORWARD -i', localIntf, '-s', root_ip.network, '-j ACCEPT' )
    root.cmd( 'iptables -A FORWARD -i', inetIntf, '-d', root_ip.network, '-j ACCEPT' )

    root.cmd( 'iptables -t nat -A POSTROUTING -o ', inetIntf, '-j MASQUERADE' )

    # Instruct the kernel to perform forwarding
    root.cmd( 'sysctl net.ipv4.ip_forward=1' )
    root.cmd( 'echo 1 /proc/sys/net/ipv4/ip_forward' )

def stopNAT( root ):
    """Stop NAT/forwarding between Mininet and external network"""
    # Flush any currently active rules
    root.cmd( 'iptables -F' )
    root.cmd( 'iptables -t nat -F' )

    # Instruct the kernel to stop forwarding
    root.cmd( 'sysctl net.ipv4.ip_forward=0' )

def fixNetworkManager( root, intf ):
    """Prevent network-manager from messing with our interface,
       by specifying manual configuration in /etc/network/interfaces
       root: a node in the root namespace (for running commands)
       intf: interface name"""
    cfile = '/etc/network/interfaces'
    line = '\niface %s inet manual\n' % intf
    config = open( cfile ).read()
    if ( line ) not in config:
        print '*** Adding', line.strip(), 'to', cfile
        with open( cfile, 'a' ) as f:
            f.write( line )
    # Probably need to restart network-manager to be safe -
    # hopefully this won't disconnect you
    root.cmd( 'systemctl restart network-manager' )

def connectToInternet( network, switch=None,
                       node_name=None,
                       ip_address='192.168.100.254/24'):
    """Connect the network to the internet
       switch: switch to connect to (internal)
       node_name: routing node name
       ip_address: ip address of the root node"""

    if switch and node_name:
        switch = network.get( switch )

        # Create a node in root namespace
        root = Node( node_name, inNamespace=False )

        ext_iface = '%s-eth0' % node_name

        # Prevent network-manager from interfering with our interface
        #fixNetworkManager( root, ext_iface )

        # Create link between root NS and switch
        link = network.addLink( root, switch )

        ip, bitmask = ip_address.split( '/' )
        link.intf1.setIP( ip, bitmask )

    return root

if __name__ == '__main__':
    lg.setLogLevel( 'info')
    net = TreeNet( depth=1, fanout=4 )
    # Configure and start NATted connectivity
    rootnode = connectToInternet( net,
                                  switch='natsw',
                                  node_name='natgw',
                                  ip_address='10.0.0.0/8' )
    print "*** Hosts are running and should have internet connectivity"
    print "*** Type 'exit' or control-D to shut down network"
    CLI( net )
    # Shut down NAT
    stopNAT( rootnode )
    net.stop()
