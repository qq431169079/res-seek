# _*_ coding: utf-8 _*_
import socket
import os,glob
import time as time_p
import requests
from bencode import bdecode, BTL
from torrent import *
import threading, signal
import MySQLdb
from BloomFilter import *

class Thunder(object):
    def __init__(self):
        self.connstr={'host':'127.0.0.1','user':'root','passwd':'123456','port':3306,'charset':"UTF8"}
    def download(self, infohash):
        try:
            tc = self._download(infohash)
            if(tc==-1):
                return
            tc = bdecode(tc)
            info = torrentInfo(tc)
            # print info['name']
            # print info['length']
            # print info['files']
            uint=int(infohash[:4]+infohash[-4:],16)
            time_now=time_p.strftime('%Y-%m-%d %H:%M:%S',time_p.localtime(time_p.time()))
            sql="insert into torrentinfo(infohash,filename,filelength,recvtime,filecontent,uinthash) values('%s','%s','%d','%s','%s','%d')"%(infohash,MySQLdb.escape_string(info['name']),info['length'],time_now,MySQLdb.escape_string(info['files']),uint)
            self.executeSQL(sql)
        except Exception,e:
            print  e
            pass

    def openConnection(self):
        try:
            self.conn=MySQLdb.connect(**self.connstr)
            self.cur=self.conn.cursor()
            self.conn.select_db('dht')
        except MySQLdb.Error,e:
            print 'mysql error %d:%s'%(e.args[0],e.args[1])


    def executeSQL(self,sql):
        try:
            self.cur.execute(sql)
            self.conn.commit()
        except MySQLdb.Error,e:
            print 'mysql error %d:%s'%(e.args[0],e.args[1])
    def closeConnection(self):
        try:
            self.cur.close()
            self.conn.close()
        except MySQLdb.Error,e:
            print 'mysql error %d:%s'%(e.args[0],e.args[1])

    def _download(self, infohash):
        infohash = infohash.upper()
        start = infohash[0:2]
        end = infohash[-2:]
        url = "http://bt.box.n0808.com/%s/%s/%s.torrent" % (start, end, infohash)
        headers = {
            "Referer": "http://bt.box.n0808.com"
        }
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                # f=open("d:\\"+infohash+'.torrent','wb')
                # f.write(r.content)
                # f.close()
                return r.content
        except (socket.timeout, requests.exceptions.Timeout), e:
            pass
        return -1

class torrentBean(object):
    """docstring for torrentBean"""
    __slots__=('infohash','filename','recvtime','filecontent','uinthash')

    def __init__(self, infohash,filename,recvtime,filecontent,uinthash):
        super(torrentBean, self).__init__()
        self.infohash = infohash
        self.filename = filename
        self.recvtime = recvtime
        self.filecontent = filecontent
        self.uinthash = uinthash


bf = BloomFilter(0.001, 1000000)
a=Thunder()
a.openConnection()
# info_hash="a02d2735e6e1daa6f7d58f21bd7340a7b7c4b7a5"
# info_hash='cf3a6a4f07da0b90beddae838462ca0012bef285'
# a.download('cf3a6a4f07da0b90beddae838462ca0012bef285')


files=glob.glob('./*.txt')
for fl in files:
    print os.path.basename(fl)
    f=open(fl,'r')
    for line in f:
        infohash=line.strip('\n')
        if not bf.is_element_exist(infohash):
            bf.insert_element(infohash)
            a.download(infohash)
a.closeConnection()