from inaugurator import partitiontable
from inaugurator import targetdevice
from inaugurator import mount
from inaugurator import sh
from inaugurator import network
from inaugurator import loadkernel
from inaugurator import fstab
from inaugurator import passwd
from inaugurator import osmosis
from inaugurator import checkinwithserver
from inaugurator import grub
from inaugurator import diskonkey
from inaugurator import udev
from inaugurator import download
import argparse
import traceback
import pdb
import os
import time


def main(args):
    before = time.time()
    udev.loadAllDrivers()
    targetDevice = targetdevice.TargetDevice.device()
    partitionTable = partitiontable.PartitionTable(targetDevice)
    if args.inauguratorClearDisk:
        partitionTable.clear()
    partitionTable.verify()
    print "Partitions created"
    mountOp = mount.Mount(targetDevice)
    checkIn = None
    with mountOp.mountRoot() as destination:
        if args.inauguratorSource == 'network':
            network.Network(
                macAddress=args.inauguratorUseNICWithMAC, ipAddress=args.inauguratorIPAddress,
                netmask=args.inauguratorNetmask, gateway=args.inauguratorGateway)
            osmos = osmosis.Osmosis(
                destination, objectStores=args.inauguratorOsmosisObjectStores,
                withLocalObjectStore=args.inauguratorWithLocalObjectStore)
            if args.inauguratorServerHostname:
                checkIn = checkinwithserver.CheckInWithServer(hostname=args.inauguratorServerHostname)
                label = checkIn.label()
            else:
                label = args.inauguratorNetworkLabel
        elif args.inauguratorSource == 'DOK':
            dok = diskonkey.DiskOnKey()
            with dok.mount() as source:
                osmos = osmosis.Osmosis(
                    destination, objectStores=source + "/osmosisobjectstore",
                    withLocalObjectStore=args.inauguratorWithLocalObjectStore)
                with open("%s/inaugurate_label.txt" % source) as f:
                    label = f.read().strip()
        else:
            assert False, "Unknown source %s" % args.inauguratorSource
        osmos.tellLabel(label)
        osmos.wait()
        print "Osmosis complete"
        with open(os.path.join(destination, "etc", "inaugurator.label"), "w") as f:
            f.write(label)
        with mountOp.mountBoot() as bootDestination:
            sh.run("rsync -rlpgDS --delete-before %s/boot/ %s/" % (destination, bootDestination))
        with mountOp.mountBootInsideRoot():
            print "Installing grub"
            grub.install(targetDevice, destination)
        print "Boot sync complete"
        fstab.createFSTab(
            rootPath=destination, root=mountOp.rootPartition(),
            boot=mountOp.bootPartition(), swap=mountOp.swapPartition())
        print "/etc/fstab created"
        if args.inauguratorChangeRootPassword:
            passwd.setRootPassword(destination, args.inauguratorChangeRootPassword)
            print "Changed root password"
        loadKernel = loadkernel.LoadKernel()
        loadKernel.fromBootPartitionGrubConfig(
            bootPath=os.path.join(destination, "boot"), rootPartition=mountOp.rootPartition(),
            append=args.inauguratorPassthrough)
        print "kernel loaded"
        if args.inauguratorDownload:
            downloadInstance = download.Download(args.inauguratorDownload)
            downloadInstance.download(destination)
    print "sync..."
    sh.run(["busybox", "sync"])
    print "sync done"
    after = time.time()
    if checkIn is not None:
        checkIn.done()
    print "Inaugurator took: %.2fs. KEXECing" % (after - before)
    loadKernel.execute()


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--inauguratorClearDisk", action="store_true")
parser.add_argument("--inauguratorSource", required=True)
parser.add_argument("--inauguratorServerHostname")
parser.add_argument("--inauguratorNetworkLabel")
parser.add_argument("--inauguratorOsmosisObjectStores")
parser.add_argument("--inauguratorUseNICWithMAC")
parser.add_argument("--inauguratorIPAddress")
parser.add_argument("--inauguratorNetmask")
parser.add_argument("--inauguratorGateway")
parser.add_argument("--inauguratorChangeRootPassword")
parser.add_argument("--inauguratorWithLocalObjectStore", action="store_true")
parser.add_argument("--inauguratorPassthrough", default="")
parser.add_argument("--inauguratorDownload", nargs='+', default=[])

try:
    cmdLine = open("/proc/cmdline").read()
    args = parser.parse_known_args(cmdLine.split(' '))[0]
    if args.inauguratorSource == "network":
        assert (
            (args.inauguratorServerHostname or args.inauguratorNetworkLabel) and
            args.inauguratorOsmosisObjectStores and
            args.inauguratorUseNICWithMAC and args.inauguratorIPAddress and
            args.inauguratorNetmask and args.inauguratorGateway), \
            "If inauguratorSource is 'network', all network command line paramaters must be specified"
    elif args.inauguratorSource == "DOK":
        pass
    else:
        assert False, "Unknown source for inaugurator: %s" % args.inauguratorSource
    main(args)
except Exception as e:
    print "Inaugurator raised exception: "
    traceback.print_exc(e)
finally:
    pdb.set_trace()
