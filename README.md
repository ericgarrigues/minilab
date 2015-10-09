# Minilab: SDN network simulator

Introduction
------------

Minilab is a mininet library extension allowing simple setup and tests of complex network topologies.

A new node class ManageableHost provides a basic pseudo container (network namespace + chrooted ssh) node type that can be manageable directly or with ansible.

Topologies are defined in yaml files (see examples/lab1/topo.yaml).


Requirements
------------

- mininet
- openvswitch
- python libraries
    - py2-ipaddress
    - pyyaml
    - jinja2

If you want to use ManageableHost class:

- linux kernel with overlaysfs support (>= 3.18)

If you want to be able to NAT your network:

- kernel with iptables support


Installation
------------

Install packages on debian/ubuntu systems (tested on ubuntu >= 14.04):

    apt-get install iptables git mininet python-pip python-jinja2 python-yaml python-pip 

Install python2 ipaddress library :

    pip install py2-ipaddress

Install minilab code :

    git clone https://github.com/ericgarrigues/minilab.git

Setup your minilab env :

The simple/auto way with ubuntu 14.04 as distribution for manageable hosts:

    cd minilab
    sudo ./setup_mlenv.sh

Test minilab
------------

It is today required to have a remote (can be on same host) openflow controller for spawned switches which, in my opinion, is the most frequent use of minilab/mininet.

I recommand ryu or opendaylight controllers as they are both well supported.

For ryu installation : http://osrg.github.io/ryu/
For opendaylight installation : https://www.opendaylight.org/

Minilab configuration
---------------------

Minilab configuration files are written in yaml.

### General configuration

By default the configuration is in the minilab directory and is named config.yaml.

You can specify another configuration file with the **--config** minilab runtime argument.

Base configuration :

```
# minilab configuration file
minilab_dir: "/var/minilab"
root_fs: "/var/minilab/rootfs"
ssh:
    template: "sshd_config.j2"
    tmpl_dir: "templates"
``` 

### Topology configuration

Topology files contain controllers, switches, hosts and links configurations.

```
# sample configuration
nat:
    node:
        name: ogw1
        ip: "192.168.100.254/24"
    switch:
        name: o1
    ext_iface: eth0
controllers:
    - name: ryu
      ip: 127.0.0.1
      port: 6653
switches:
    - name: s1
      dpid: "0000000000000001"
    - name: s2
      dpid: "0000000000000002"
      links:
          - s1
    - name: s3
      dpid: "0000000000000003"
      links:
          - s1
          - s2
    - name: o1
      dpid: "0000000000000004"
hosts:
    - name: h1
      is_manageable: True
      gw: 192.168.100.254
      links:
          - sw: s1
            ip: "172.16.0.1/16"
          - sw: o1
            ip: "192.168.100.1/24"
    - name: h2
      is_manageable: True
      gw: 192.168.100.254
      links:
          - sw: s2
            ip: "172.16.0.2/16"
          - sw: o1
            ip: "192.168.100.2/24"
    - name: h3
      is_manageable: True
      gw: 192.168.100.254
      links:
          - sw: v1
            ip: "172.16.0.3/16"
          - sw: o1
            ip: "192.168.100.3/24"
```

Test with minimal ryu controller configuration
----------------------------------------------

TO WRITE

Connect remotely into the manageable hosts
------------------------------------------

You can easily access your hosts with a simple ssh configuration (~/.ssh/config) like this:

```
Host minilab
    user root
    Hostname my.minilab.host
    IdentityFile ~/.ssh/my_ssh_key

Host 192.168.100.*
    user root
    ServerAliveInterval    60
    TCPKeepAlive           yes
    ProxyCommand           ssh -q -A root@minilab nc %h %p
    ControlMaster          auto
    ControlPath            ~/.ssh/mux-%r@%h:%p
    ControlPersist         8h
    User                   root
```

Your public ssh key must be present in your /root/.ssh/authorized_keys of the minilab host.

Managing ManageableHosts with ansible:
--------------------------------------

TO WRITE

Hosting minilab in Gandi (service provider i work for):
-------------------------------------------------------

TO WRITE

Example topology 
----------------

![alt tag](examples/loop/loop.png)

TODO
----

- remove dependancy on py-ipaddress


