import socket, struct, sys

def query(domain, server=('127.0.0.1', 53)):
    q = b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
    for label in domain.split('.'):
        q += bytes([len(label)]) + label.encode()
    q += b'\x00' + struct.pack('!HH', 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(3)
    s.sendto(q, server)
    data, _ = s.recvfrom(512)
    # parse answers
    p = 12
    while data[p] != 0:
        p += data[p] + 1
    p += 1 + 4  # NUL + qtype/qclass
    answers = []
    while p + 15 < len(data):
        p += 1  # name pointer 0xc00c
        p += 1
        typ = int.from_bytes(data[p:p+2], 'big'); p += 2
        cls = int.from_bytes(data[p:p+2], 'big'); p += 2
        ttl = int.from_bytes(data[p:p+4], 'big'); p += 4
        ln = int.from_bytes(data[p:p+2], 'big'); p += 2
        rdata = data[p:p+ln]; p += ln
        answers.append('.'.join(str(b) for b in rdata) if ln == 4 else f'type{typ} len{ln}')
    return answers

for dom in ['ecode.np.cs.playstation.net', 'manuals.playstation.net', 'ps5.np.playstation.net']:
    try:
        print(f'{dom} -> {query(dom)}')
    except Exception as e:
        print(f'{dom} -> ERROR: {e}')
