# encoding: utf-8

from hashlib import sha1
from random import randint
from struct import unpack, pack
from socket import inet_aton, inet_ntoa
from bisect import bisect_left
from threading import Timer
from time import sleep

from bencode import bencode, bdecode

BOOTSTRAP_NODES = [
    ("router.bittorrent.com", 6881),
    ("dht.transmissionbt.com", 6881),
    ("router.utorrent.com", 6881)
]
TID_LENGTH = 4
KRPC_TIMEOUT = 10
REBORN_TIME = 5 * 60
K = 8


def entropy(bytes):
    s = ""
    for i in range(bytes):
        s += chr(randint(0, 255))
    return s

    # """把爬虫"伪装"成正常node, 一个正常的node有ip, port, node ID三个属性, 因为是基于UDP协议,
    # 所以向对方发送信息时, 即使没"明确"说明自己的ip和port时, 对方自然会知道你的ip和port,
    # 反之亦然. 那么我们自身node就只需要生成一个node ID就行, 协议里说到node ID用sha1算法生成,
    # sha1算法生成的值是长度是20 byte, 也就是20 * 8 = 160 bit, 正好如DHT协议里说的那范围: 0 至 2的160次方,
    # 也就是总共能生成1461501637330902918203684832716283019655932542976个独一无二的node.
    # ok, 由于sha1总是生成20 byte的值, 所以哪怕你写SHA1(20)或SHA1(19)或SHA1("I am a 2B")都可以,
    # 只要保证大大降低与别人重复几率就行. 注意, node ID非十六进制,
    # 也就是说非FF5C85FE1FDB933503999F9EB2EF59E4B0F51ECA这个样子, 即非hash.hexdigest(). """


def random_id():
    hash = sha1()
    hash.update(entropy(20))
    return hash.digest()


def decode_nodes(nodes):
    n = []
    length = len(nodes)
    if (length % 26) != 0:
        return n
    for i in range(0, length, 26):
        nid = nodes[i:i + 20]
        ip = inet_ntoa(nodes[i + 20:i + 24])
        port = unpack("!H", nodes[i + 24:i + 26])[0]
        n.append((nid, ip, port))
    return n


def encode_nodes(nodes):
    strings = []
    for node in nodes:
        s = "%s%s%s" % (node.nid, inet_aton(node.ip), pack("!H", node.port))
        strings.append(s)

    return "".join(strings)


def intify(hstr):
    # """这是一个小工具, 把一个node ID转换为数字. 后面会频繁用到."""
    return long(hstr.encode('hex'), 16)  # 先转换成16进制, 再变成数字


def timer(t, f):
    Timer(t, f).start()


class BucketFull(Exception):
    pass


class KRPC(object):
    def __init__(self):
        self.types = {
            "r": self.response_received,
            "q": self.query_received
        }
        self.actions = {
            "ping": self.ping_received,
            "find_node": self.find_node_received,
            "get_peers": self.get_peers_received,
            "announce_peer": self.announce_peer_received,
        }

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(("0.0.0.0", self.port))

    def response_received(self, msg, address):
        self.find_node_handler(msg)

    def query_received(self, msg, address):
        try:
            self.actions[msg["q"]](msg, address)
        except KeyError:
            pass

    def send_krpc(self, msg, address):
        try:
            self.socket.sendto(bencode(msg), address)
        except:
            pass


class Client(KRPC):
    def __init__(self, table):
        self.table = table

        timer(KRPC_TIMEOUT, self.timeout)
        timer(REBORN_TIME, self.reborn)
        KRPC.__init__(self)

    def find_node(self, address, nid=None):
        nid = self.get_neighbor(nid) if nid else self.table.nid
        tid = entropy(TID_LENGTH)

        msg = {
            "t": tid,
            "y": "q",
            "q": "find_node",
            "a": {"id": nid, "target": random_id()}
        }
        self.send_krpc(msg, address)

    def find_node_handler(self, msg):
        try:
            nodes = decode_nodes(msg["r"]["nodes"])
            for node in nodes:
                (nid, ip, port) = node
                if len(nid) != 20: continue
                if nid == self.table.nid: continue
                self.find_node((ip, port), nid)
        except KeyError:
            pass

    def joinDHT(self):
        for address in BOOTSTRAP_NODES:
            self.find_node(address)

    def timeout(self):
        if len(self.table.buckets) < 2:
            self.joinDHT()
        timer(KRPC_TIMEOUT, self.timeout)

    def reborn(self):
        self.table.nid = random_id()
        self.table.buckets = [KBucket(0, 2 ** 160)]
        timer(REBORN_TIME, self.reborn)

    def start(self):
        self.joinDHT()

        while True:
            try:
                (data, address) = self.socket.recvfrom(65536)
                msg = bdecode(data)
                self.types[msg["y"]](msg, address)
            except Exception:
                pass

    def get_neighbor(self, target):
        return target[:10] + random_id()[10:]


class Server(Client):
    def __init__(self, master, table, port):
        self.table = table
        self.master = master
        self.port = port
        Client.__init__(self, table)

    def ping_received(self, msg, address):
        try:
            nid = msg["a"]["id"]
            msg = {
                "t": msg["t"],
                "y": "r",
                "r": {"id": self.get_neighbor(nid)}
            }
            self.send_krpc(msg, address)
            self.find_node(address, nid)
        except KeyError:
            pass

    def find_node_received(self, msg, address):
        try:
            target = msg["a"]["target"]
            neighbors = self.table.get_neighbors(target)

            nid = msg["a"]["id"]
            msg = {
                "t": msg["t"],
                "y": "r",
                "r": {
                    "id": self.get_neighbor(target),
                    "nodes": encode_nodes(neighbors)
                }
            }
            self.table.append(KNode(nid, *address))
            self.send_krpc(msg, address)
            self.find_node(address, nid)
        except KeyError:
            pass

    def get_peers_received(self, msg, address):
        try:
            infohash = msg["a"]["info_hash"]

            neighbors = self.table.get_neighbors(infohash)

            nid = msg["a"]["id"]
            msg = {
                "t": msg["t"],
                "y": "r",
                "r": {
                    "id": self.get_neighbor(infohash),
                    "nodes": encode_nodes(neighbors)
                }
            }
            self.table.append(KNode(nid, *address))
            self.send_krpc(msg, address)
            self.master.log(infohash)
            self.find_node(address, nid)
        except KeyError:
            pass

    def announce_peer_received(self, msg, address):
        try:
            infohash = msg["a"]["info_hash"]
            nid = msg["a"]["id"]

            msg = {
                "t": msg["t"],
                "y": "r",
                "r": {"id": self.get_neighbor(infohash)}
            }

            self.table.append(KNode(nid, *address))
            self.send_krpc(msg, address)
            self.master.log(infohash)
            self.find_node(address, nid)
        except KeyError:
            pass


# 该类只实例化一次.
class KTable(object):
    # 这里的nid就是通过node_id()函数生成的自身node ID. 协议里说道, 每个路由表至少有一个bucket,
    #    还规定第一个bucket的min=0, max=2^160次方, 所以这里就给予了一个buckets属性来存储bucket, 这个是列表.
    def __init__(self, nid):
        self.nid = nid
        self.buckets = [KBucket(0, 2 ** 160)]

    def append(self, node):
        index = self.bucket_index(node.nid)
        try:
            bucket = self.buckets[index]
            bucket.append(node)
        except IndexError:
            return
        except BucketFull:
            if not bucket.in_range(self.nid):
                return
            self.split_bucket(index)
            self.append(node)

        # 返回与目标node ID或infohash的最近K个node.

        # 定位出与目标node ID或infohash所在的bucket, 如果该bucuck有K个节点, 返回.
        # 如果不够到K个节点的话, 把该bucket前面的bucket和该bucket后面的bucket加起来, 只返回前K个节点.
        # 还是不到K个话, 再重复这个动作. 要注意不要超出最小和最大索引范围.
        # 总之, 不管你用什么算法, 想尽办法找出最近的K个节点.

    def get_neighbors(self, target):
        nodes = []
        if len(self.buckets) == 0: return nodes
        if len(target) != 20: return nodes

        index = self.bucket_index(target)
        try:
            nodes = self.buckets[index].nodes
            min = index - 1
            max = index + 1

            while len(nodes) < K and ((min >= 0) or (max < len(self.buckets))):
                if min >= 0:
                    nodes.extend(self.buckets[min].nodes)

                if max < len(self.buckets):
                    nodes.extend(self.buckets[max].nodes)

                min -= 1
                max += 1

            num = intify(target)
            nodes.sort(lambda a, b, num=num: cmp(num ^ intify(a.nid), num ^ intify(b.nid)))
            return nodes[:K]  # K是个常量, K=8
        except IndexError:
            return nodes

    def bucket_index(self, target):
        return bisect_left(self.buckets, intify(target))

        # 拆表

        # index是待拆分的bucket(old bucket)的所在索引值.
        # 假设这个old bucket的min:0, max:16. 拆分该old bucket的话, 分界点是8, 然后把old bucket的max改为8, min还是0.
        # 创建一个新的bucket, new bucket的min=8, max=16.
        # 然后根据的old bucket中的各个node的nid, 看看是属于哪个bucket的范围里, 就装到对应的bucket里.
        # 各回各家,各找各妈.
        # new bucket的所在索引值就在old bucket后面, 即index+1, 把新的bucket插入到路由表里.

    def split_bucket(self, index):
        old = self.buckets[index]
        point = old.max - (old.max - old.min) / 2
        new = KBucket(point, old.max)
        old.max = point
        self.buckets.insert(index + 1, new)
        for node in old.nodes[:]:
            if new.in_range(node.nid):
                new.append(node)
                old.remove(node)

    def __iter__(self):
        for bucket in self.buckets:
            yield bucket


class KBucket(object):
    __slots__ = ("min", "max", "nodes")

    # min和max就是该bucket负责的范围, 比如该bucket的min:0, max:16的话,
    # 那么存储的node的intify(nid)值均为: 0到15, 那16就不负责, 这16将会是该bucket后面的bucket的min值.
    # nodes属性就是个列表, 存储node. last_accessed代表最后访问时间, 因为协议里说到,
    # 当该bucket负责的node有请求, 回应操作; 删除node; 添加node; 更新node; 等这些操作时,
    # 那么就要更新该bucket, 所以设置个last_accessed属性, 该属性标志着这个bucket的"新鲜程度". 用linux话来说, touch一下.
    # 这个用来便于后面说的定时刷新路由表.

    def __init__(self, min, max):
        self.min = min
        self.max = max
        self.nodes = []

    # 添加node, 参数node是KNode实例.

    # 如果新插入的node的nid属性长度不等于20, 终止.
    # 如果满了, 抛出bucket已满的错误, 终止. 通知上层代码进行拆表.
    # 如果未满, 先看看新插入的node是否已存在, 如果存在, 就替换掉, 不存在, 就添加,
    # 添加/替换时, 更新该bucket的"新鲜程度".
    def append(self, node):
        if node in self:
            self.remove(node)
            self.nodes.append(node)
        else:
            if len(self) < K:
                self.nodes.append(node)
            else:
                raise BucketFull

    def remove(self, node):
        self.nodes.remove(node)

    def in_range(self, target):
        return self.min <= intify(target) < self.max

    def __len__(self):
        return len(self.nodes)

    def __contains__(self, node):
        return node in self.nodes

    def __iter__(self):
        for node in self.nodes:
            yield node

    def __lt__(self, target):
        return self.max <= target


class KNode(object):
    # """
    #       nid就是node ID的简写, 就不取id这么模糊的变量名了. __init__方法相当于别的OOP语言中的构造方法,
    #       在python严格来说不是构造方法, 它是初始化, 不过, 功能差不多就行.
    #       """
    __slots__ = ("nid", "ip", "port")

    def __init__(self, nid, ip, port):
        self.nid = nid
        self.ip = ip
        self.port = port

    def __eq__(self, other):
        return self.nid == other.nid


# using example
class Master(object):
    def __init__(self, f):
        self.f = f

    def log(self, infohash):
        self.f.write(infohash.encode("hex") + "\n")
        self.f.flush()

try:
    f = open("infohash.log","a")
    m = Master(f)
    s = Server(Master(f), KTable(random_id()), 8001)
    s.start()
except KeyboardInterrupt:
    s.socket.close()
    f.close()