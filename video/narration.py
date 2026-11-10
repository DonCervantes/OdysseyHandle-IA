"""New narration from measured evidence. Secrets stay in memory; paid calls are cached by content."""
from __future__ import annotations
import hashlib,json,subprocess,sys
from pathlib import Path
from dotenv import dotenv_values
import httpx
ROOT=Path(subprocess.check_output(['git','rev-parse','--path-format=absolute','--git-common-dir'],text=True).strip()).parent
OUT=ROOT/'var/video'
def pct(v):return f'{v*100:.1f}'.replace('.', ' coma ')
def money(v):return f'{round(v):,}'.replace(',',' ')
def number_es(value):
    """Small integer formatter for counts in this experiment (no measured literals)."""
    n=int(value)
    small=['cero','uno','dos','tres','cuatro','cinco','seis','siete','ocho','nueve','diez','once','doce','trece','catorce','quince']
    if 0<=n<len(small):return small[n]
    if n>=1000 and n%1000==0:return ('mil' if n==1000 else number_es(n//1000)+' mil')
    return str(n)

def script(e):
    s=e['summary'];c=e['case'];p=e['patch'];h=e['hypothesis']
    # Slots follow the official 40 / 65 / 75-second structure. Last 2 s have no voice.
    return [
    dict(id='01',start=0,end=16,title='Las reglas fijas repiten el error',text='En México, siete de cada diez vehículos circulan sin seguro, según la AMIS. Y una tarifa con reglas fijas cobra mal a segmentos enteros. AutoGuard aprende de ese error. Esta demo usa datos simulados.'),
    dict(id='02',start=16,end=40,title='Un caso reservado revela la falla',text=f"Este {c['marca']} {c['modelo']} viene del conjunto reservado. Las reglas fijas cotizan {money(c['quotes']['v0'])} pesos; el costo observado fue {money(c['costo_real'])}. El analista detecta subcotización de {pct(abs(h['sesgo_medio']))} por ciento en {h['n']} autos de alto kilometraje. Penalizamos más cobrar de menos: buscamos el cuantil cero punto seis del costo, no su media."),
    dict(id='03',start=40,end=64,title='La lección queda guardada',text=f"La lección propone reajustar el factor de kilometraje. Aquí están la hipótesis, el cambio del YAML y su commit. En el conjunto reservado, la pérdida media baja de {money(p['metrics_before']['loss'])} a {money(p['metrics_after']['loss'])} pesos. El evaluador congelado acepta: mejora suficiente y ningún segmento excede el límite de deterioro."),
    dict(id='04',start=64,end=84,title='El sucesor hereda el cambio',text=f"El sucesor hereda esa configuración y cotiza el mismo auto en {money(c['quotes']['sucesor'])} pesos. Cambió la regla del cotizador; no el auto ni su costo. Cada lección aceptada queda en el linaje. Se acumulan versiones, lecciones y posteriors que orientan qué mejora intentar después."),
    dict(id='05',start=84,end=105,title='Sistema y equipo tienen papeles distintos',text='El equipo fijó la pérdida, los umbrales, el simulador y la lista blanca. El sistema detectó, propuso, evaluó y aceptó. El meta mejorador aprende de aciertos y rechazos. En producción, el actuario aprobaría aquí. Este botón muestra la intervención humana; la corrida experimental automatiza las decisiones.'),
    dict(id='06',start=105,end=130,title='Mismos autos, tres formas de aprender',text=f"Comparamos {number_es(s['batches']*s['batch_size'])} autos por variante, con la misma semilla. Regret significa aquí pérdida asimétrica acumulada. Reglas fijas: {s['regret']['estatico']/1e6:.2f} millones; solo parámetros: {s['regret']['parametros']/1e6:.2f}; erre ese i completo: {s['regret']['rsi']/1e6:.2f}. Reduce {pct(s['mejora_rsi'])} por ciento. En {number_es(len(e['seeds']))} semillas, la mejora va de {min(x['mejora'] for x in e['seeds'])} a {max(x['mejora'] for x in e['seeds'])} por ciento. Estos casos reservados nunca entraron al mejorador."),
    dict(id='07',start=130,end=150,title='Sin la lección, vuelve la falla',text=f"Aislamos el efecto: revertimos solo esa primera lección en una copia del linaje. La prima vuelve a {money(c['quotes']['reversion'])} pesos y regresa la pérdida original. La variante solo parámetros es nuestro control. Esta reversión prueba el cambio local; no atribuye toda la mejora final a un único parche."),
    dict(id='08',start=150,end=166,title='Lo que todavía falla',text=f"El resultado final sigue {pct(s['exceso_final_vs_oraculo']['rsi'])} por ciento sobre el oráculo. No aprendió la interacción de autos de treinta años con un siniestro. La aceptación termina en {number_es(s['tasa_aceptacion_rsi']['ultima']*100)}. No alcanzamos la meta del cuarenta por ciento ni la convergencia estricta."),
    dict(id='09',start=166,end=180,title='Construido desde cero con evidencia',text='Codex construyó linaje, ciclo y tableros, y revisó entregas. Claude Code y Cursor también participaron. Scripts y relevo coordinaron al equipo. Empezamos desde cero este nueve de noviembre.')]

def main():
    e=json.loads((OUT/'evidence.json').read_text());segments=script(e)
    env=dotenv_values(ROOT/'.env');audio_dir=OUT/'audio';audio_dir.mkdir(exist_ok=True)
    required=['ELEVENLABS_API_KEY','ELEVENLABS_VOICE_ID','ELEVENLABS_MODEL_ID']
    if not all(env.get(k) for k in required):raise SystemExit('Faltan credenciales ElevenLabs en .env; no se imprimen valores.')
    for seg in segments:
        text=seg['text'].replace('erre ese i','erre ese i')
        key=hashlib.sha256((env['ELEVENLABS_VOICE_ID']+env['ELEVENLABS_MODEL_ID']+text).encode()).hexdigest()
        path=audio_dir/(seg['id']+'.mp3');stamp=path.with_suffix('.sha256')
        if not(path.exists() and stamp.exists() and stamp.read_text()==key):
            response=httpx.post('https://api.elevenlabs.io/v1/text-to-speech/'+env['ELEVENLABS_VOICE_ID'],headers={'xi-api-key':env['ELEVENLABS_API_KEY']},params={'output_format':'mp3_44100_128'},json={'text':text,'model_id':env['ELEVENLABS_MODEL_ID'],'language_code':'es'},timeout=180)
            if response.status_code!=200:
                # Do not log request headers, response body or credential-containing URLs.
                raise SystemExit(f'ElevenLabs rechazó sección {seg["id"]}: HTTP {response.status_code}. Sin salida de secretos.')
            path.write_bytes(response.content);stamp.write_text(key)
        duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=nw=1:nk=1',str(path)],text=True))
        target=seg['end']-seg['start']-(2 if seg['id']=='09' else 0.5)
        tempo=max(1,duration/target)
        seg.update(raw_duration=duration,tempo=tempo,audio=f'audio/{seg["id"]}.wav')
        if tempo>1.20:raise SystemExit(f'Sección {seg["id"]} demasiado larga ({duration:.1f}s para {target}s): abreviar guion, no acelerar más.')
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(path),'-af',f'atempo={tempo},loudnorm=I=-16:TP=-1.5:LRA=11','-ar','48000',str(path.with_suffix('.wav'))],check=True)
        print(f'Voz {seg["id"]}: {duration:.2f}s, tempo {tempo:.3f}',flush=True)
    (OUT/'narration.json').write_text(json.dumps(segments,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
