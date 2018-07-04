# _*_ coding: utf-8 _*_
from time import time

def torrentInfo(torrentContent):
    metadata = torrentContent["info"]
    print metadata
    info = {
        "name": getName(metadata),
        "length": calcLength(metadata),
        "timestamp": getCreateDate(torrentContent),
        "files": extraFiles(metadata)
    }
    return info

def calcLength(metadata):
    length = 0
    try:
        length = metadata["length"]
    except KeyError:
        try:
            for file in metadata["files"]:
                length += file["length"]
        except KeyError:
            pass
    return length

def extraFiles(metadata):
    files = []
    try:
        for file in metadata["files"]:
            path = file["path.utf-8"]
            size=file['length']
            if len(path) > 1:
                main = path[0]
                for f in path[1:2]:
                    files.append("%s/%s    %d bytes" % (main, f,size))
            else:
                files.append("%s    %d bytes" % (path[0],size) )
        if files:
            return '\r\n'.join(files)
        else:
            return getName(metadata)
    except KeyError:
        return getName(metadata)

def getName(metadata):
    try:
        name = metadata["name.utf-8"]
        if name.strip()=="":
                raise KeyError
    except KeyError:
        try:
            name = metadata["name"]
            if name.strip()=="":
                raise KeyError
        except KeyError:
            name = getMaxFile(metadata)

    return name
def getMaxFile(metadata):
    try:
        maxFile = metadata["files"][0]
        for file in metadata["files"]:
            if file["length"] > maxFile["length"]:
                maxFile = file
        name = maxFile["path"][0]
        return name
    except KeyError:
        return ""

def getCreateDate(torrentContent):
    try:
        timestamp = torrentContent["creation date"]
    except KeyError:
        timestamp = int( time() )
    return timestamp