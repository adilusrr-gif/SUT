import os
import tempfile
from pathlib import Path
_test_dir = tempfile.TemporaryDirectory(prefix='sut-test-')
os.environ['DATABASE_URL']='sqlite:///' + str(Path(_test_dir.name)/'test.db')
os.environ['APP_ACCESS_TOKEN']='local-test-access-' + 'x'*40
os.environ['OPENAI_API_KEY']=''
os.environ['DEMO_SEED']='true'
