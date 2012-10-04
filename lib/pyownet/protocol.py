"""this module is a first try to implement the ownet protocol"""

import struct
import socket

# socket buffer
_SCK_BUF = 1024

# do not attempt to read messages bigger than this
MAX_PAYLOAD = _SCK_BUF

# see msg_classification from ow_message.h
MSG_ERROR = 0
MSG_NOP = 1
MSG_READ = 2
MSG_WRITE = 3
MSG_DIR = 4
MSG_PRESENCE = 6
MSG_DIRALL = 7
MSG_GET = 8
MSG_DIRALLSLASH = 9
MSG_GETSLASH = 10

# see http://owfs.org/index.php?page=owserver-flag-word
# and ow_parsedname.h
FLG_BUS_RET =     0x00000002
FLG_PERSISTENCE = 0x00000004
FLG_ALIAS =       0x00000008
FLG_SAFEMODE =    0x00000010
FLG_UNCACHED =    0x00000020
FLG_OWNET =       0x00000100

# look for 
# 'enum temp_type' in ow_temperature.h
# 'enum pressure_type' in ow_pressure.h
# 'enum deviceformat' in ow.h
MSK_TEMPSCALE =     0x00030000
MSK_PRESSURESCALE = 0x001C0000
MSK_DEVFORMAT =     0xFF000000

FLG_TEMP_C =        0x00000000
FLG_TEMP_F =        0x00010000
FLG_TEMP_K =        0x00020000
FLG_TEMP_R =        0x00030000

FLG_PRESS_MBAR =    0x00000000
FLG_PRESS_ATM =     0x00040000
FLG_PRESS_MMHG =    0x00080000
FLG_PRESS_INHG =    0x000C0000
FLG_PRESS_PSI =     0x00100000
FLG_PRESS_PA =      0x00140000

FLG_FORMAT_FDI =    0x00000000 #  /10.67C6697351FF
FLG_FORMAT_FI =     0x01000000 #  /1067C6697351FF
FLG_FORMAT_FDIDC =  0x02000000 #  /10.67C6697351FF.8D
FLG_FORMAT_FDIC  =  0x03000000 #  /10.67C6697351FF8D
FLG_FORMAT_FIDC =   0x04000000 #  /1067C6697351FF.8D
FLG_FORMAT_FIC =    0x05000000 #  /1067C6697351FF8D


class Error(Exception):
    pass


class HostError(Error):

    def __init__(self, reason):
        self.reason = reason

class ShortRead(Error):
    pass


class ShortWrite(Error):
    pass


class DataError(Error):
    pass


class _Header(str):
    """base class for ownet protocol headers"""

    _format = struct.Struct(">iiiiii")
    hsize = _format.size

    def __new__(cls, *args, **kwargs):
        if args:
            msg = args[0]
            # FIXME check for args type and semantics
            assert len(args)==1
            assert not kwargs
            assert isinstance(msg, str)
            assert len(msg) == cls.hsize
            #
            vals = cls._format.unpack(msg)
        else:
            vals = tuple(map(kwargs.pop, cls._fields, cls._defaults))
            if kwargs:
                print dir()
                raise TypeError(
  "__new__() got an unexpected keyword argument '%s'" % kwargs.popitem()[0] )
            msg = cls._format.pack(*vals)
        self = super(_Header, cls).__new__(cls, msg)
        assert isinstance(vals, tuple)
        self._vals = vals
        return self

    def __repr__(self):
        repr = self.__class__.__name__ + '('
        repr += ', '.join(map(lambda x: '%s=%s' % x, 
                            zip(self._fields, self._vals)))
        repr += ')'
        return repr


class _addfieldprops(type):
    """metaclass for adding properties"""

    @staticmethod
    def _getter(i):
        return lambda x: x._vals[i]

    def __new__(mcs, name, bases, dict):
        for i, j in enumerate(dict['_fields']):
            dict[j] = property(mcs._getter(i))
        return type.__new__(mcs, name, bases, dict)


class ServerHeader(_Header):
    """client to server request header"""

    __metaclass__ = _addfieldprops
    _fields = ('version', 'payload', 'type', 'flags', 'size', 'offset')
    _defaults = (0, 0, MSG_NOP, FLG_OWNET, _SCK_BUF, 0)


class ClientHeader(_Header):
    """server to client reply header"""

    __metaclass__ = _addfieldprops
    _fields = ('version', 'payload', 'ret', 'flags', 'size', 'offset')
    _defaults = (0, 0, 0, FLG_OWNET, 0, 0)


class OwnetClientConnection(object):

    def __init__(self, sockaddr, verbose=False):
        """establish a connection with server at sockaddr"""
        
        self.verbose = verbose
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect(sockaddr)
        self.sock.settimeout(1.0)
        if self.verbose:
            print self.sock.getsockname()

    def __del__(self):

        pass

    def request(self, header, payload):
        """
        FIXME
        """
        self.send_msg(header, payload)
        rep, data = self.read_msg()
        self.sock.close()
        return rep, data

    def send_msg(self, header, payload):
        """
        FIXME
        """

        if self.verbose:
            print '->', repr(header)
            print '..', repr(payload)
        assert header.payload == len(payload)
        sent = self.sock.send(header + payload)
        if sent < len(header + payload):
            raise ShortWrite
        assert sent == len(header + payload), sent
        
    def read_msg(self):
        """
        FIXME
        """

        header = self.sock.recv(ClientHeader.hsize)
        if len(header) < ClientHeader.hsize:
            raise ShortRead('Error reading ClientHeader, got %s' % repr(header))
        assert(len(header) == ClientHeader.hsize)
        header = ClientHeader(header)
        if self.verbose: 
            print '<-', repr(header)
        if header.version != 0 or header.payload > MAX_PAYLOAD:
            raise DataError('got malformed header: %s "%s"' % 
                                    (repr(header), header))
        if header.payload > 0:
            payload = self.sock.recv(header.payload)
            if len(payload) < header.payload:
                raise ShortRead('got %s' % repr(header)+':'+repr(payload))
            if self.verbose: 
                print '..', repr(payload)
            assert header.size <= header.payload
            payload = payload[:header.size]
        else:
            payload = ''
        return header, payload
    

class OwnetProxy(object):
    """proxy owserver"""

    def __init__(self, host='localhost', port=4304, verbose=False):
        try:
            gai = socket.getaddrinfo(host, port, 
                  socket.AF_INET, socket.SOCK_STREAM, socket.SOL_TCP)
        except socket.gaierror as exp:
            raise HostError(exp)
        self._sockaddr = gai[0][4]
        self.verbose = verbose

    def _send_request(self, header, payload):
        sess = OwnetClientConnection(self._sockaddr, self.verbose)
        return sess.request(header, payload)

    def ping(self):
        """check connection"""
        resp, data =  self._send_request(ServerHeader(),'')
        if (resp, data) != (ClientHeader(), ''):
            raise DataError(repr(resp))

    def dir(self, path):
        """li = dir(path)"""
        # build message
        path += '\x00'
        sheader = ServerHeader(payload=len(path), type=MSG_DIRALLSLASH)
        # chat
        cheader, data = self._send_request(sheader, path)
        # check reply
        if cheader.ret < 0:
            raise DataError(repr(cheader))
        if data:
            return data.split(',')
        else:
            return []

    def read(self, path):
        """val = read(path)"""
        # build message
        path += '\x00'
        sheader = ServerHeader(payload=len(path), type=MSG_READ)
        # chat
        cheader, data = self._send_request(sheader, path)
        # chek reply
        if cheader.ret < 0:
            raise DataError(repr(cheader))
        return data


def test():
    proxy = OwnetProxy(verbose=True)
    proxy.dir('/')
    proxy.read('/26.B4FF64000000/temperature')
    proxy.read('/26.52A664000000/temperature')

if __name__ == '__main__':
    test()
