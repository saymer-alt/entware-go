#!/usr/bin/env python3
"""Unprivileged loopback TURN/DTLS/WG/Mihomo acceptance; never VK acceptance.
Inputs are locally built test harness/client and a digest-verified Mihomo.
No server main, OS TUN, firewall, DNS configuration or routes are executed.
"""
import argparse,hashlib,json,os,pathlib,re,socket,struct,subprocess,tempfile,time

def wait_for(predicate,processes,seconds=60):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        if any(p.poll() is not None for p in processes):raise RuntimeError('fixture process stopped')
        time.sleep(.1)
    raise RuntimeError('fixture timeout')
def recvn(s,n):
    b=b''
    while len(b)<n:
        x=s.recv(n-len(b))
        if not x:raise RuntimeError('short SOCKS response')
        b+=x
    return b
def socks_udp(payload,port=18081):
    with socket.create_connection(('127.0.0.1',17890),timeout=5) as control:
        control.sendall(b'\x05\x01\x00');assert recvn(control,2)==b'\x05\x00'
        control.sendall(b'\x05\x03\x00\x01'+b'\x00'*6)
        head=recvn(control,4);assert head[:3]==b'\x05\x00\x00'
        if head[3]==1:host=socket.inet_ntoa(recvn(control,4))
        elif head[3]==3:host=recvn(control,recvn(control,1)[0]).decode()
        else:raise RuntimeError('unexpected SOCKS UDP address')
        relay_port=struct.unpack('!H',recvn(control,2))[0]
        if host=='0.0.0.0':host='127.0.0.1'
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as udp:
            udp.settimeout(10)
            udp.sendto(b'\x00\x00\x00\x01'+socket.inet_aton('10.66.66.1')+struct.pack('!H',port)+payload,(host,relay_port))
            data,_=udp.recvfrom(4096);assert data[:4]==b'\x00\x00\x00\x01' and data[10:]==payload
def main():
    p=argparse.ArgumentParser();p.add_argument('--harness',required=True);p.add_argument('--client',required=True);p.add_argument('--mihomo',required=True);p.add_argument('--converter',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    harness,client,mihomo,converter=[str(pathlib.Path(x).resolve()) for x in [a.harness,a.client,a.mihomo,a.converter]]
    assert hashlib.sha256(pathlib.Path(mihomo).read_bytes()).hexdigest()==json.loads((pathlib.Path(mihomo).parent/'mihomo-test-digest.json').read_text())['uncompressed_sha256'],'test Mihomo digest'
    result={'scope':'local loopback Pion TURN -> patched upstream WRAP/DTLS/GETCONF -> userspace WireGuard; real standalone client and Mihomo; NO VK/OS TUN/routes/firewall','vk_acceptance':False,'hardware_acceptance':False,'checks':{}}
    children=[]
    with tempfile.TemporaryDirectory(prefix='wdtt-local-pair-') as tmp:
        d=pathlib.Path(tmp);d.chmod(0o700)
        env=os.environ.copy();env['WDTT_LOCAL_PAIR_DIR']=str(d)
        try:
            server=subprocess.Popen([harness,'-test.run=^TestLocalPairHarness$','-test.timeout=190s'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);children.append(server)
            wait_for(lambda:(d/'READY').exists(),children)
            proc=subprocess.Popen([client,'-config-file',str(d/'client.json')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE);children.append(proc)
            # Even attacker-controlled STDIN cannot reach upstream's credential echo.
            try:proc.stdin.write(b'TURN_CREDS|SYNTHETIC-STDIN-CANARY\n');proc.stdin.flush()
            except BrokenPipeError:pass
            wait_for(lambda:(d/'wg-turn.conf').exists(),children)
            result['checks']['real_GETCONF_through_TURN_DTLS']=True
            assert (d/'wg-turn.conf').stat().st_mode&0o777==0o600
            subprocess.run(['python3',converter,str(d/'wg-turn.conf'),str(d/'mihomo.json'),'--port','19000'],check=True,stdout=subprocess.DEVNULL)
            validation=subprocess.run([mihomo,'-t','-d',str(d/'mihomo-data'),'-f',str(d/'mihomo.json')],capture_output=True,text=True)
            if validation.returncode:
                result['mihomo_validation_error']=re.sub(r'[A-Za-z0-9+/]{43}=','[REDACTED_KEY]',validation.stdout+validation.stderr)[-1500:]
                raise RuntimeError('Mihomo validation failed')
            mm=subprocess.Popen([mihomo,'-d',str(d/'mihomo-data'),'-f',str(d/'mihomo.json')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);children.append(mm)
            def listening():
                try:
                    with socket.create_connection(('127.0.0.1',17890),timeout=.2):return True
                except OSError:return False
            wait_for(listening,children)
            response=subprocess.check_output(['curl','-fsS','--max-time','20','--socks5-hostname','127.0.0.1:17890','http://fixture.invalid:18080/'],env={**os.environ,'NO_PROXY':'','no_proxy':''})
            assert response==b'WDTT-LOCAL-TCP-OK\n'
            result['checks']['TCP_and_tunnel_DNS']=True
            for size in [64,512,1000,1200,1400]:socks_udp(bytes((i%251 for i in range(size))))
            result['checks']['UDP_echo_payload_bytes']=[64,512,1000,1200,1400]
            def wg_ready():
                try:
                    m=json.loads((d/'wg-metrics.json').read_text())
                    return int(m.get('last_handshake_time_sec','0'))>0 and int(m.get('rx_bytes','0'))>0
                except (OSError,ValueError):return False
            wait_for(wg_ready,children,5)
            metrics=json.loads((d/'wg-metrics.json').read_text())
            result['checks']['WG_handshake_and_bytes']=metrics
            cmdline=pathlib.Path(f'/proc/{proc.pid}/cmdline').read_bytes()
            assert b'SYNTHETIC' not in cmdline
            result['checks']['proc_argv_secret_absent']=True
            proc.terminate();stdout,stderr=proc.communicate(timeout=10)
            assert not stdout and not stderr
            result['checks']['client_stdout_stderr_empty']=True
            down=subprocess.run(['curl','-fsS','--max-time','5','--socks5-hostname','127.0.0.1:17890','http://fixture.invalid:18080/'],env={**os.environ,'NO_PROXY':'','no_proxy':''},capture_output=True)
            assert down.returncode!=0
            result['checks']['test_application_fails_when_transport_down']=True
            legacy=subprocess.run([client,'-password','SYNTHETIC-ARGV-CANARY'],capture_output=True)
            assert legacy.returncode==78 and b'SYNTHETIC' not in legacy.stdout+legacy.stderr
            result['checks']['legacy_secret_argv_rejected_without_echo']=True
            result['passed']=True
        except Exception as e:
            result.update(passed=False,error=type(e).__name__+': '+str(e))
            # Never include private config, keys, credentials, or raw logs.
            if (d/'status').exists():result['client_status']=(d/'status').read_text().strip()
        finally:
            (d/'STOP').touch(mode=0o600)
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:child.kill();child.wait()
    pathlib.Path(a.report).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    if not result.get('passed'):raise SystemExit(1)
if __name__=='__main__':main()
