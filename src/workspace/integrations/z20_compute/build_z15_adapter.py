"""Independent auxiliary adapter package; original Z15 files are reference copies."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
MODULES=('__init__.py','protocol.py','environment.py','link.py','service.py','training.py','npu.py',
         'z15_client.py','z15_feature_tap.py','z15_preflight.py')
ORIGINALS=('cyton_fatigue.py','cyton_sqi.py','seed_shadow_policy.py','seed_gate_policy.py',
           'seed_quality_runtime.py','seed_replay_check.py','seed_shadow_weights.npz',
           'cyton_fatigue_overlap4.json')
README='''# Z15 辅助计算适配包

这是独立目录中的适配副本。真实 Z15 安装和原控制链回归待板卡恢复后进行。
`reference_original` 只用于版本核对，不覆盖现有运行文件。

先解包到新目录，在该目录运行：

```
python -m z20_compute.z15_preflight --legacy-dir /实际的原脑电运行目录
```

预检核对原模型与预处理源码摘要。若版本不同，保留差异，先检查原工程；
不要用参考副本替换实际文件。新目录无需安装 SciPy；原采集程序继续使用自身依赖。

在原脑电程序已经创建情绪、疲劳分类器后，暂停采集循环并安装观察钩子：

```python
from z20_compute.z15_client import ReconnectingFeatures
from z20_compute.z15_feature_tap import FeatureTap
aux = ReconnectingFeatures("192.168.1.20", 9020)
aux.start()
tap = FeatureTap(aux, source="live:Z15").attach(emotion=原情绪实例, fatigue=原疲劳实例)
# 恢复原采集循环。录制回放时将 source 改为 recorded:具体录音标识。
```

该钩子观察原分类器实际使用的 180 维／20 维向量。原返回值保留，网络故障
只增加辅助发布的丢弃计数。连接恢复后建立新会话，离线特征不补发。
用 `aux.result("emotion")`、`aux.result("fatigue")` 读取有效且未过期结果；
无结果返回 None。结果只交给汇总展示，保持原眼控、S3 9000 和执行权限。

回退：暂停原采集循环，调用 `tap.close()`、`aux.close()`，再恢复原循环。
这会移除实例上的观察钩子。此包没有修改原源码、模型、网络配置或启动项。
正式接入点须在真实 Z15 版本预检通过后安装，不要另起串口采集器。
'''


def create_bundle(output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    payload={('z20_compute/'+name):(HERE/'z20_compute'/name).read_bytes() for name in MODULES}
    original=HERE.parents[1]/'multimodal/vendor/runtime'
    hashes={}
    for name in ORIGINALS:
        data=(original/name).read_bytes();payload['reference_original/'+name]=data
        hashes[name]=hashlib.sha256(data).hexdigest()
    payload['original_hashes.json']=json.dumps(hashes,indent=2).encode()
    payload['config.example.json']=json.dumps(dict(enabled=False,host='192.168.1.20',port=9020,
        source='recorded:replace-with-recording-id',autostart=False,actuator_control=False),indent=2).encode()
    payload['README.md']=README.encode('utf-8')
    payload['SHA256.json']=json.dumps({name:hashlib.sha256(data).hexdigest() for name,data in payload.items()},indent=2).encode()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in payload.items():archive.writestr(name,data)
    return output


if __name__=='__main__':
    path=create_bundle(HERE/'artifacts/z15_auxiliary_adapter.zip')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
