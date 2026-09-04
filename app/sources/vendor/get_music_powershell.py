"""
使用 PowerShell 获取当前播放的音乐信息
无需安装额外的Python库，直接使用Windows系统功能
"""

import subprocess
import json
import sys
import base64


# PowerShell 脚本用于获取媒体信息
POWERSHELL_SCRIPT = """
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null

$sessionManager = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])

$currentSession = $sessionManager.GetCurrentSession()

if ($null -eq $currentSession) {
    $errorJson = @{
        status = "no_media"
        message = "当前没有媒体正在播放"
    } | ConvertTo-Json -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($errorJson)
    $base64 = [Convert]::ToBase64String($bytes)
    Write-Output $base64
    exit 0
}

$mediaProperties = Await ($currentSession.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])

$playbackInfo = $currentSession.GetPlaybackInfo()
$playbackStatus = $playbackInfo.PlaybackStatus
$positionSeconds = $null
$durationSeconds = $null
try {
    $timeline = $currentSession.GetTimelineProperties()
    if ($null -ne $timeline) {
        $positionSeconds = [Math]::Max(0, $timeline.Position.TotalSeconds)
        $durationSeconds = [Math]::Max(0, ($timeline.EndTime - $timeline.StartTime).TotalSeconds)
    }
} catch {
    # 有些播放器不发布时间线；保留为空，由上层安全降级
}

$statusMap = @{
    0 = "已关闭"
    1 = "正在打开"
    2 = "正在改变"
    3 = "已停止"
    4 = "正在播放"
    5 = "已暂停"
}

$info = @{
    status = "success"
    app_name = $currentSession.SourceAppUserModelId
    title = $mediaProperties.Title
    artist = $mediaProperties.Artist
    album_title = $mediaProperties.AlbumTitle
    album_artist = $mediaProperties.AlbumArtist
    track_number = $mediaProperties.TrackNumber
    playback_status = $statusMap[[int]$playbackStatus]
    playback_status_code = [int]$playbackStatus
    position = $positionSeconds
    duration = $durationSeconds
}

$json = $info | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
$base64 = [Convert]::ToBase64String($bytes)
Write-Output $base64
"""


# 带封面提取的 PowerShell 脚本
POWERSHELL_THUMBNAIL_SCRIPT = """
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}

[Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStreamWithContentType, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null

$sessionManager = Await ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])

$currentSession = $sessionManager.GetCurrentSession()

if ($null -eq $currentSession) {
    $errorJson = @{
        status = "no_media"
        message = "当前没有媒体正在播放"
        thumbnail_base64 = $null
    } | ConvertTo-Json -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($errorJson)
    $base64 = [Convert]::ToBase64String($bytes)
    Write-Output $base64
    exit 0
}

$mediaProperties = Await ($currentSession.TryGetMediaPropertiesAsync()) ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])

$playbackInfo = $currentSession.GetPlaybackInfo()
$playbackStatus = $playbackInfo.PlaybackStatus
$positionSeconds = $null
$durationSeconds = $null
try {
    $timeline = $currentSession.GetTimelineProperties()
    if ($null -ne $timeline) {
        $positionSeconds = [Math]::Max(0, $timeline.Position.TotalSeconds)
        $durationSeconds = [Math]::Max(0, ($timeline.EndTime - $timeline.StartTime).TotalSeconds)
    }
} catch {
    # 有些播放器不发布时间线；保留为空，由上层安全降级
}

$statusMap = @{
    0 = "已关闭"
    1 = "正在打开"
    2 = "正在改变"
    3 = "已停止"
    4 = "正在播放"
    5 = "已暂停"
}

# 获取封面 Base64
$thumbnailBase64 = $null
try {
    $thumbnail = $mediaProperties.Thumbnail
    if ($null -ne $thumbnail) {
        $stream = Await ($thumbnail.OpenReadAsync()) ([Windows.Storage.Streams.IRandomAccessStreamWithContentType])
        if ($null -ne $stream) {
            $asStreamMethod = [System.IO.WindowsRuntimeStreamExtensions].GetMethods() | Where-Object {
                $_.Name -eq 'AsStreamForRead' -and $_.GetParameters().Count -eq 1
            } | Select-Object -First 1

            if ($null -ne $asStreamMethod) {
                $netStream = $asStreamMethod.Invoke($null, @($stream))
                $memStream = New-Object System.IO.MemoryStream
                $netStream.CopyTo($memStream)
                $imgBytes = $memStream.ToArray()
                if ($imgBytes.Length -gt 0) {
                    $thumbnailBase64 = [Convert]::ToBase64String($imgBytes)
                }
                try { $memStream.Dispose() } catch {}
                try { $netStream.Dispose() } catch {}
            }
            try { $stream.Dispose() } catch {}
        }
    }
} catch {
    # 封面获取失败不影响主流程（但不重置已获取到的数据）
}

$info = @{
    status = "success"
    app_name = $currentSession.SourceAppUserModelId
    title = $mediaProperties.Title
    artist = $mediaProperties.Artist
    album_title = $mediaProperties.AlbumTitle
    album_artist = $mediaProperties.AlbumArtist
    track_number = $mediaProperties.TrackNumber
    playback_status = $statusMap[[int]$playbackStatus]
    playback_status_code = [int]$playbackStatus
    position = $positionSeconds
    duration = $durationSeconds
    thumbnail_base64 = $thumbnailBase64
}

$json = $info | ConvertTo-Json -Compress
$bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
$base64 = [Convert]::ToBase64String($bytes)
Write-Output $base64
"""


def get_playing_music_with_thumbnail():
    """
    使用 PowerShell 获取当前播放的音乐信息（包含封面）
    
    返回:
        dict: 包含歌曲信息和封面 Base64 的字典
    """
    try:
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', POWERSHELL_THUMBNAIL_SCRIPT],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=15
        )
        
        if result.returncode != 0:
            return {
                'status': 'error',
                'message': f'PowerShell 执行失败: {result.stderr}',
                'thumbnail_base64': None
            }
        
        output = result.stdout.strip()
        
        if not output:
            return {
                'status': 'error',
                'message': 'PowerShell 未返回任何输出',
                'thumbnail_base64': None
            }
        
        try:
            json_bytes = base64.b64decode(output)
            json_str = json_bytes.decode('utf-8')
            info = json.loads(json_str)
            return info
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Base64 解码失败: {str(e)}',
                'thumbnail_base64': None
            }
        
    except subprocess.TimeoutExpired:
        return {
            'status': 'error',
            'message': 'PowerShell 执行超时',
            'thumbnail_base64': None
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'发生错误: {str(e)}',
            'thumbnail_base64': None
        }


def get_playing_music():
    """
    使用 PowerShell 获取当前播放的音乐信息
    
    返回:
        dict: 包含歌曲信息的字典
    """
    try:
        # 运行 PowerShell 脚本，输出为 Base64 编码
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', POWERSHELL_SCRIPT],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=10
        )
        
        if result.returncode != 0:
            return {
                'status': 'error',
                'message': f'PowerShell 执行失败: {result.stderr}'
            }
        
        output = result.stdout.strip()
        
        if not output:
            return {
                'status': 'error',
                'message': 'PowerShell 未返回任何输出'
            }
        
        # 解码 Base64
        try:
            json_bytes = base64.b64decode(output)
            json_str = json_bytes.decode('utf-8')
            info = json.loads(json_str)
            return info
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Base64 解码失败: {str(e)}'
            }
        
    except subprocess.TimeoutExpired:
        return {
            'status': 'error',
            'message': 'PowerShell 执行超时'
        }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'发生错误: {str(e)}'
        }


def format_music_info(info):
    """
    格式化输出音乐信息
    
    参数:
        info: get_playing_music() 返回的字典
    """
    if info['status'] == 'no_media':
        print(f"\n⚠️  {info['message']}")
        return
    
    if info['status'] == 'error':
        print(f"\n❌ {info['message']}")
        return
    
    print("\n" + "="*60)
    print("🎵 当前播放信息")
    print("="*60)
    
    # 解析应用名称
    app_id = info['app_name']
    app_display_name = app_id.split('!')[-1] if '!' in app_id else app_id
    
    # 常见应用名称映射
    app_name_map = {
        'QQMusic': 'QQ音乐',
        'NeteaseCloudMusic': '网易云音乐',
        'Spotify': 'Spotify',
        'AIMP': 'AIMP',
        'foobar2000': 'foobar2000',
    }
    
    display_name = app_name_map.get(app_display_name, app_display_name)
    print(f"播放器: {display_name}")
    print(f"播放状态: {info['playback_status']}")
    print(f"\n歌曲标题: {info['title'] or '未知'}")
    print(f"艺术家: {info['artist'] or '未知'}")
    print(f"专辑: {info['album_title'] or '未知'}")
    
    if info.get('album_artist'):
        print(f"专辑艺术家: {info['album_artist']}")
    
    if info.get('track_number'):
        print(f"曲目编号: {info['track_number']}")
    
    print("="*60 + "\n")


def monitor_music(interval=2):
    """
    持续监控当前播放的音乐（每隔指定秒数检查一次）
    
    参数:
        interval: 检查间隔（秒）
    """
    import time
    
    print("🎧 开始监控音乐播放... (按 Ctrl+C 停止)")
    print(f"检查间隔: {interval} 秒\n")
    
    last_title = None
    error_count = 0
    
    try:
        while True:
            info = get_playing_music()
            
            if info['status'] == 'success':
                error_count = 0  # 重置错误计数
                current_title = info['title']
                
                # 只在歌曲改变时输出完整信息
                if current_title != last_title:
                    format_music_info(info)
                    last_title = current_title
                else:
                    # 状态变化时简单提示
                    status = info['playback_status']
                    if status == '正在播放':
                        print(f"⏯️  {current_title}", end='\r')
                    elif status == '已暂停':
                        print(f"⏸️  {current_title} (已暂停)", end='\r')
                        
            elif info['status'] == 'no_media':
                if last_title is not None:  # 从有音乐变为无音乐
                    print(f"\n⚠️  播放已停止")
                    last_title = None
                    
            else:  # 错误
                error_count += 1
                if error_count == 1:  # 只显示第一次错误
                    print(f"\n❌ {info['message']}")
                if error_count >= 5:  # 连续5次错误则退出
                    print("\n连续发生多次错误，停止监控")
                    break
            
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n✅ 监控已停止")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='获取Windows系统当前正在播放的音乐信息 (PowerShell方案)'
    )
    parser.add_argument(
        '--monitor', '-m',
        action='store_true',
        help='持续监控模式'
    )
    parser.add_argument(
        '--interval', '-i',
        type=int,
        default=2,
        help='监控模式下的检查间隔（秒，默认2秒）'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='以JSON格式输出结果（适合程序调用）'
    )
    parser.add_argument(
        '--thumbnail',
        action='store_true',
        help='同时获取专辑封面（Base64编码），需配合 --json 使用'
    )
    
    args = parser.parse_args()
    
    if args.monitor:
        # 监控模式
        monitor_music(args.interval)
    else:
        # 单次查询模式
        if args.thumbnail:
            info = get_playing_music_with_thumbnail()
        else:
            info = get_playing_music()
        
        if args.json:
            # JSON 输出模式 - 强制使用UTF-8编码输出
            import sys
            json_str = json.dumps(info, ensure_ascii=False, indent=2)
            # 直接写入二进制stdout，确保UTF-8编码
            sys.stdout.buffer.write(json_str.encode('utf-8'))
            sys.stdout.buffer.flush()
        else:
            # 格式化输出模式
            format_music_info(info)
