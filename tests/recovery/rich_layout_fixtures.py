"""Anonymous geometry and export-matrix cases for measured layout QA."""

from io import BytesIO

from PIL import Image

from packages.resume_core.models.rich_document import RichDocumentV1


def block(id, text='', kind='paragraph', children=(), props=None, content=None):
    return {'id':id,'revision':1,'type':kind,'props':props or {},'children':list(children),'provenance':[],
        'content':content if content is not None else [{'type':'text','text':text,'styles':{}}]}


def section(id,text,children,**props):
    return block(id,text,'section',children,{'recordId':None,**props})


def fixture(kind='short'):
    labels=['Python','C#','PostgreSQL','Redis','Kafka','RabbitMQ','Docker','Go (Golang)','Kubernetes','Distributed systems']
    sidebar=[section('focus','FOCUS',[block('focus-'+str(i),label) for i,label in enumerate(labels)],presentation='focus'),
        section('education','ОБРАЗОВАНИЕ',[block('education-1','Учебный технический университет. Информатика, 2016.')]),
        section('languages','ЯЗЫКИ',[block('language-1','Русский — родной. Английский — B2.')])]
    profile=section('profile','О СЕБЕ',[block('profile-text','Разрабатываю сервисы.\nПишу понятный код.\nРаботаю с командой.\nПроверяю результат.')])
    jobs=[]
    for i in range(5 if kind=='long' else 1):
        children=[block(f'job-{i}-heading',f'Компания {i+1} — инженер-программист','heading',props={'level':2}),
            block(f'job-{i}-date','Январь 2020 — декабрь 2022'),block(f'job-{i}-stack','Python, PostgreSQL, Docker')]
        count=22 if kind=='long' else 3
        children += [block(f'job-{i}-task-{j}',f'Задача {i+1}.{j+1}: разработала сервис и проверила результат.', 'bullet_list') for j in range(count)]
        children.append(block(f'job-{i}-end',f'JOB_END_{i+1}'))
        jobs.append(section(f'job-{i}','',children))
    main=[profile,section('experience','ОПЫТ',jobs),section('skills','НАВЫКИ',[block('skills-body','Архитектура, интеграции и автоматизация. FINAL_MARKER')])]
    images={}
    if kind=='matrix':
        from tests.recovery.test_rich_structural_export import merged
        main += [block('link','',content=[{'type':'link','href':'https://example.com/'+('long-path-'*120),
            'content':[{'type':'text','text':'Exact link '+('адрес'*80),'styles':{'italic':True,'underline':True,'textColor':'#334455'}}]}]),
            block('check-on','Проверено','check_list',props={'checked':True}),block('check-off','Не проверено','check_list',props={'checked':False}),
            block('quote','Цитата с выделением','quote',props={'backgroundColor':'#EEEEDD'}),
            block('toggle','Раскрытая группа','toggle_list',[block('toggle-child','TOGGLE_CHILD')]),
            block('code','',kind='code',props={'language':'python'},content='def example():\n    return "Кириллица"\nCODE_END'),
            block('divider','',kind='divider',content=None),
            block('table','',kind='table',content=merged())]
        main[-2]['content']=None
        nested=block('depth-10','DEPTH_END','numbered_list',props={'start':9})
        for depth in reversed(range(10)):
            nested=block('depth-'+str(depth),'Вложенный список '+str(depth),'numbered_list',[nested],{'start':1})
        main.append(nested)
        png=BytesIO();Image.new('RGB',(320,160),(34,102,153)).save(png,format='PNG');images['qa-image']=png.getvalue()
        main.append(block('image','',kind='image',content=None,props={'assetId':'qa-image','width':300,'height':150,'alignment':'center','alt':'QA diagram',
            'caption':[{'type':'text','text':'IMAGE_CAPTION','styles':{'bold':True}}]}));main[-1]['content']=None
        main.append(block('matrix-end','MATRIX_END'))
    document=RichDocumentV1.model_validate({'schemaVersion':1,'revision':1,'regions':[
        {'id':'header','role':'header','revision':1,'blocks':[block('name','Дмитрий Примеров','heading',props={'level':1}),block('title','Инженер-программист','heading',props={'level':2})]},
        {'id':'sidebar','role':'sidebar','revision':1,'blocks':sidebar},
        {'id':'main','role':'main','revision':1,'blocks':main}]})
    return document,images
