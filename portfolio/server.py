import asyncio
import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from fractions import Fraction
from pathlib import Path

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCBundlePolicy, AudioStreamTrack
from av import AudioFrame
from src_core.utils.validate import validate_sdp
from portfolio.runtime import DemoRuntime

ROOT = Path(__file__).parent/'web'
SECRET = os.environ.get('PORTFOLIO_SECRET','')
TURN_SECRET = os.environ.get('TURN_SECRET','')
PUBLIC_IP = os.environ.get('PUBLIC_IP','62.113.112.185')
sessions = {}


class MockTone(AudioStreamTrack):
    """Short synthetic tone is explicitly a TTS placeholder, never synthesized speech."""
    def __init__(self):
        super().__init__()
        self.pts=0
        self.started=None
        self.tone_until=0

    async def recv(self):
        if self.started is None:self.started=time.monotonic()
        await asyncio.sleep(max(0,self.started+self.pts/48000-time.monotonic()))
        import array
        samples=array.array('h',(int(1800*math.sin(2*math.pi*440*(self.pts+i)/48000)) if time.monotonic()<self.tone_until else 0 for i in range(960)))
        frame=AudioFrame(format='s16',layout='mono',samples=960)
        frame.planes[0].update(samples.tobytes());frame.sample_rate=48000;frame.pts=self.pts;frame.time_base=Fraction(1,48000);self.pts+=960
        return frame


@web.middleware
async def boundary(request, handler):
    if not request.path.startswith('/api/'):
        return await handler(request)
    token=request.cookies.get('portfolio_voice','');parts=token.split('.')
    valid=len(parts)==3 and len(parts[0])==48 and parts[1].isdigit() and int(parts[1])>time.time() and hmac.compare_digest(hmac.new(SECRET.encode(),'.'.join(parts[:2]).encode(),'sha256').hexdigest(),parts[2])
    if not valid:
        raw=secrets.token_hex(24)+'.'+str(int(time.time())+3600);token=raw+'.'+hmac.new(SECRET.encode(),raw.encode(),'sha256').hexdigest()
    request['owner']=hashlib.sha256(token.encode()).hexdigest()
    try:response=await handler(request)
    except web.HTTPException as exc:response=web.json_response({'error':exc.reason},status=exc.status)
    except (ValueError,KeyError,TypeError):response=web.json_response({'error':'Некорректный запрос'},status=400)
    if not valid:response.set_cookie('portfolio_voice',token,max_age=3600,secure=True,httponly=True,samesite='Lax')
    response.headers['Cache-Control']='no-store'
    return response


async def close(owner):
    session=sessions.pop(owner,None)
    if session:
        for task in session['tasks']:
            if task is not asyncio.current_task():task.cancel()
        session['tone'].stop()
        await session['pc'].close()


def send(session, value):
    channel=session.get('channel')
    if channel and channel.readyState=='open':channel.send(json.dumps(value,ensure_ascii=False))


async def handle_message(owner,message):
    session=sessions.get(owner)
    if not session:return
    if not isinstance(message,str) or len(message)>1024:return send(session,{'type':'error','message':'Сообщение превышает лимит'})
    if session['busy']:return send(session,{'type':'error','message':'Дождитесь текущего ответа'})
    try:payload=json.loads(message)
    except ValueError:return send(session,{'type':'error','message':'Некорректный JSON'})
    if not isinstance(payload,dict) or set(payload)-{'type','text'}:return send(session,{'type':'error','message':'Неподдерживаемый контракт'})
    if payload.get('type')=='reset':
        session['runtime']=DemoRuntime()
        return send(session,{'type':'reset','message':'Контекст этой сессии очищен'})
    if payload.get('type')=='asr':
        if session['frames']<10:return send(session,{'type':'error','message':'Сначала передайте аудио с микрофона'})
        text='Проверка голосового канала'
        send(session,{'type':'asr_mock','text':text,'message':'Фиксированная фраза мока ASR; это не распознавание вашей речи'})
    elif payload.get('type')=='text':text=payload.get('text','')
    else:return send(session,{'type':'error','message':'Неизвестный тип сообщения'})
    if not isinstance(text,str) or not 1<=len(text.strip())<=280:return send(session,{'type':'error','message':'Введите от 1 до 280 символов'})
    if session['turns']>=10:return send(session,{'type':'error','message':'Лимит: 10 сообщений на короткую сессию'})
    session['busy']=True;session['turns']+=1
    send(session,{'type':'processing','message':'Исходный LangGraph обрабатывает сообщение'})
    try:
        result=await session['runtime'].run(text.strip())
        session['tone'].tone_until=time.monotonic()+0.35
        send(session,{'type':'answer',**result,'mockTts':'Короткий тон вместо синтезированной речи'})
    except asyncio.TimeoutError:send(session,{'type':'timeout','message':'Таймаут мока LLM: граф отменён через 2 секунды. Можно повторить запрос.'})
    except Exception:send(session,{'type':'error','message':'Ошибка сценария. Сбросьте свой пример и повторите.'})
    finally:session['busy']=False


async def receive_audio(session,track):
    try:
        while True:
            await track.recv();session['frames']+=1
    except Exception:return


async def expiry(owner, expected):
    await asyncio.sleep(90)
    session=sessions.get(owner)
    if session is expected:
        send(session,{'type':'expired','message':'90 секунд истекли. Соединение и контекст удалены.'})
        await close(owner)


def public_candidates(sdp):
    lines=[]
    for line in sdp.splitlines():
        if line.startswith('a=candidate:'):
            parts=line.split()
            if len(parts)<6 or parts[4]!=PUBLIC_IP:continue
        lines.append(line)
    return '\r\n'.join(lines)+'\r\n'


async def config(request):
    username=str(int(time.time())+120)+':'+request['owner'][:16]+':'+secrets.token_hex(4)
    credential=base64.b64encode(hmac.new(TURN_SECRET.encode(),username.encode(),'sha1').digest()).decode()
    return web.json_response({'iceServers':[{'urls':[f'turn:{PUBLIC_IP}:3478?transport=udp',f'turn:{PUBLIC_IP}:3478?transport=tcp'],'username':username,'credential':credential}],'iceTransportPolicy':'relay','sessionSeconds':90,'maxSessions':2})


async def offer(request):
    payload=await request.json()
    if not isinstance(payload,dict) or set(payload)!={'sdp','type'} or payload['type']!='offer' or not isinstance(payload['sdp'],str):raise web.HTTPBadRequest(reason='Ожидается SDP offer')
    ok,error=validate_sdp(payload['sdp'])
    if not ok:raise web.HTTPBadRequest(reason=error)
    media=[line for line in payload['sdp'].splitlines() if line.startswith('m=')]
    if len(media)>2 or sum(line.startswith('m=audio ') for line in media)!=1 or any(not line.startswith(('m=audio ','m=application ')) for line in media):raise web.HTTPBadRequest(reason='Разрешены только один аудиопоток и DataChannel')
    owner=request['owner']
    if owner in sessions:raise web.HTTPConflict(reason='Сначала завершите свою текущую сессию')
    if len(sessions)>=2:raise web.HTTPTooManyRequests(reason='Заняты обе голосовые сессии. Повторите через минуту.')
    pc=RTCPeerConnection(RTCConfiguration(iceServers=[],bundlePolicy=RTCBundlePolicy.MAX_BUNDLE))
    tone=MockTone();session={'pc':pc,'tone':tone,'runtime':DemoRuntime(),'frames':0,'turns':0,'messages':0,'busy':False,'tasks':[],'created':time.time()};sessions[owner]=session
    pc.addTrack(tone)
    @pc.on('track')
    def on_track(track):
        if track.kind=='audio':session['tasks'].append(asyncio.create_task(receive_audio(session,track)))
    @pc.on('datachannel')
    def on_channel(channel):
        if channel.label!='portfolio' or session.get('channel'):channel.close();return
        session['channel']=channel
        @channel.on('message')
        def on_message(message):
            session['messages']+=1
            if session['messages']>40:return channel.close()
            session['tasks']=[x for x in session['tasks'] if not x.done()]
            session['tasks'].append(asyncio.create_task(handle_message(owner,message)))
    @pc.on('connectionstatechange')
    async def state_change():
        if pc.connectionState in {'failed','closed'} and sessions.get(owner) is session:await close(owner)
    try:
        await pc.setRemoteDescription(RTCSessionDescription(sdp=public_candidates(payload['sdp']),type='offer'))
        await pc.setLocalDescription(await pc.createAnswer())
        session['tasks'].append(asyncio.create_task(expiry(owner,session)))
        return web.json_response({'sdp':public_candidates(pc.localDescription.sdp),'type':'answer','sessionSeconds':90})
    except Exception:
        await close(owner);raise web.HTTPBadRequest(reason='Не удалось согласовать WebRTC')


async def status(request):
    session=sessions.get(request['owner'])
    return web.json_response({'active':bool(session),'connection':session['pc'].connectionState if session else 'closed','receivedAudioFrames':session['frames'] if session else 0,'turns':session['turns'] if session else 0,'remainingSeconds':max(0,int(90-(time.time()-session['created']))) if session else 0,'source':'aiortc receive loop; no audio stored','at':time.time()})


async def stop(request):
    await close(request['owner']);return web.json_response({'closed':True,'contextDeleted':True})


async def home(request):return web.FileResponse(ROOT/'index.html')
async def health(request):return web.json_response({'status':'ready','activeSessions':len(sessions),'maxSessions':2})
async def shutdown(app):
    for owner in list(sessions):await close(owner)

def create_app():
    if len(SECRET)<32 or len(TURN_SECRET)<32:raise RuntimeError('Signing and TURN secrets required')
    app=web.Application(middlewares=[boundary],client_max_size=65536)
    app.router.add_get('/',home);app.router.add_get('/healthz',health);app.router.add_static('/assets',ROOT)
    app.router.add_get('/api/config',config);app.router.add_post('/api/offer',offer);app.router.add_get('/api/status',status);app.router.add_delete('/api/session',stop);app.on_shutdown.append(shutdown)
    return app

if __name__=='__main__':web.run_app(create_app(),host='127.0.0.1',port=18406,access_log=None)
