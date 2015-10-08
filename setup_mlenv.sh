#!/bin/bash

ML_FILE_PATH=/var/minilab
ML_ROOTFS_PATH=$ML_FILE_PATH/rootfs
MH_ROOTFS_FILE="ubuntu-core-14.04.3-core-amd64.tar.gz"
MH_ROOTFS_URL="http://cdimage.ubuntu.com/ubuntu-core/releases/14.04/release"
NH_DNS_SERVER="8.8.8.8"

if [ ! -d $ML_FILE_PATH ]; then
    echo "Creating $ML_FILE_PATH directory";
    mkdir $ML_FILE_PATH;
fi

if [ ! -d $ML_ROOTFS_PATH ]; then
    echo "Creating $ML_ROOTFS_PATH directory";
    mkdir $ML_ROOTFS_PATH;
    echo "Downloading and decompressing base rootfs";
    wget $MH_ROOTFS_URL/$MH_ROOTFS_FILE;
    tar -zxvf $MH_ROOTFS_FILE -C $ML_ROOTFS_PATH
    echo "Installing valid resolv.conf file in rootfs";
    echo "nameserver $NH_DNS_SERVER" > $ML_ROOTFS_PATH/etc/resolv.conf
    echo "Updating packages list in rootfs";
    chroot $ML_ROOTFS_PATH apt-get update;
    echo "Installing openssh server in rootfs";
    chroot $ML_ROOTFS_PATH apt-get install -y openssh-server;
    echo "Cleaning";
    rm -f $MH_ROOTFS_FILE;
fi

echo "Setup done"



  
