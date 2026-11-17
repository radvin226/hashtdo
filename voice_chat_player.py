import rubpy
import time
import asyncio
import pathlib
import logging

try:
    import aiortc
    from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
    from aiortc.contrib.media import MediaPlayer
except ImportError:
    aiortc = None


class VoiceChatConnection:
    def __init__(self, peer_connection, media_player, audio_track, chat_guid, voice_chat_id, client):
        self.pc = peer_connection
        self.player = media_player
        self.track = audio_track
        self.chat_guid = chat_guid
        self.voice_chat_id = voice_chat_id
        self.client = client

    def stop(self):
        if self.player:
            try:
                self.player.audio.stop()
            except Exception:
                pass
        if self.pc:
            asyncio.create_task(self.pc.close())
        if hasattr(self, '_speaking_task'):
            self._speaking_task.cancel()
        if hasattr(self, '_heartbeat_task'):
            self._heartbeat_task.cancel()

    def pause(self):
        self.track.pause()

    def resume(self):
        self.track.resume()

    def replace_track(self, new_media_path: str, loop: bool = False):
        new_player = MediaPlayer(str(new_media_path), decode=True)
        new_track = new_player.audio
        sender = next((s for s in self.pc.getSenders() if s.track and s.track.kind == "audio"), None)
        if sender:
            sender.replaceTrack(new_track)
            self.track = new_track
            self.player = new_player
        else:
            raise RuntimeError("Audio sender not found in RTCPeerConnection.")

    def get_info(self):
        return {
            "chat_guid": self.chat_guid,
            "voice_chat_id": self.voice_chat_id,
            "connection_state": self.pc.connectionState,
            "ice_state": self.pc.iceConnectionState,
        }


class VoiceChatPlayer:
    logger = logging.getLogger("VoiceChatPlayer")

    async def heartbeat(self, chat_guid: str, voice_chat_id: str) -> None:
        while True:
            try:
                await self.get_group_voice_chat_updates(chat_guid, voice_chat_id, int(time.time()))
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(5)

    async def speaking(self, chat_guid: str, voice_chat_id: str) -> None:
        while True:
            try:
                await self.send_group_voice_chat_activity(chat_guid, voice_chat_id)
                await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(2)

    async def voice_chat_player(self, chat_guid: str, media: pathlib.Path):
        if aiortc is None:
            self.logger.error("aiortc is not available.")
            return None

        class AudioFileTrack(MediaStreamTrack):
            kind = "audio"
            def __init__(self, player):
                super().__init__()
                self.player = player
                self._paused = False
            async def recv(self):
                while self._paused:
                    await asyncio.sleep(0.1)
                return await self.player.audio.recv()
            def pause(self):
                self._paused = True
            def resume(self):
                self._paused = False

        chat_info = await self.get_info(chat_guid)
        voice_chat_id = None
        try:
            voice_chat_id = chat_info.chat.find_keys('group_voice_chat_id')
        except Exception:
            pass

        if voice_chat_id is None:
            voice_chat = await self.create_group_voice_chat(chat_guid)
            try:
                voice_chat_id = voice_chat.find_keys('voice_chat_id')
            except Exception:
                try:
                    voice_chat_id = voice_chat.group_voice_chat_update.voice_chat_id
                except Exception:
                    pass

        self.logger.info(f"[VoiceChat] Starting in {chat_guid} id={voice_chat_id}")

        pc = RTCPeerConnection()
        media_player = MediaPlayer(str(media), decode=True)
        track = AudioFileTrack(media_player)
        pc.addTrack(track)

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)

        connect = await self.join_voice_chat(chat_guid, voice_chat_id, offer.sdp)
        sdp_answer = connect.sdp_answer_data

        await self.set_voice_chat_state(chat_guid, voice_chat_id)

        self._speaking_task = asyncio.create_task(self.speaking(chat_guid, voice_chat_id))
        self._heartbeat_task = asyncio.create_task(self.heartbeat(chat_guid, voice_chat_id))

        await pc.setRemoteDescription(RTCSessionDescription(sdp_answer, "answer"))

        return VoiceChatConnection(
            peer_connection=pc,
            media_player=media_player,
            audio_track=track,
            chat_guid=chat_guid,
            voice_chat_id=voice_chat_id,
            client=self
        )
