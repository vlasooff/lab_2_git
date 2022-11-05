1 commit
2 commit
from django.utils.translation import gettext as _

from django.shortcuts import render,redirect 
 
from datetime import datetime 
import datetime as datet
from authorize.notification import send_notification, send_owner_notification 
from work.utils import url_parse_2gis, url_parse_flamp,handle_uploaded_file,url_parse_create_order, cheack_all_works_nickname,to_json  
from .models import *  
import json  
#apps 
from .worker import cheack_review_2gis, cheack_review_avito, get_close_works, get_new_works, get_wait_works, get_work_works, set_nojob, set_nowork_job
from django.views.decorators.csrf  import csrf_exempt 
from django.db.models import Q

def work(request: HttpRequest) -> JsonResponse:    
    if request.user.is_authenticated is False:
        return redirect('authorize/')
     
    user = ProfileUser.get_user(request.user.id_tg) 
    if('page' in request.GET):
        
        page = request.GET['page']
        if('new' in page):
            worker = get_new_works(user)
        elif ('work' in page):
            worker = get_work_works(user)
        elif ('wait' in page):
            worker = get_wait_works(user)
        elif ('close' in page):
            worker = get_close_works(user)
        context = {'works':worker.works,'message':worker.message}
        return render(request=request,
                    template_name='work/work_all.html',
                    context=context) 
    
    worker = get_new_works(user)
    context = {'works':worker.works,'message':worker.message}
    return render(request=request,
                template_name='work/work_all.html',
                context=context) 
        

def set_user_work(request: HttpRequest) -> JsonResponse:
    data = json.loads(request.body)  
    if('id_job' not in data):
        return JsonResponse({'error':'ID_job parameter not set'},status=200)  
        

    if request.user.is_authenticated is False:
        return JsonResponse({'error':f"No authenticated"},status=500)  
    user = ProfileUser.get_user(request.user.id_tg) 

    job = Job.objects.filter(id=data['id_job'])
    if(job.exists() is False):
        return JsonResponse({'error':f"Not found job id:{data['id_job']}"},status=200)  
    
    job = job.first()
    if(job.status != 'do' and job.user_job != user):
        return JsonResponse({'error':f"Working:{data['id_job']}"},status=200)   
    job.set_work_user(user)
    job.date_public = datetime.now()
    job.save()
    workJob = WorkJob.objects.create( 
            user = user,
            job = job, 
        )  
    send_notification(job.push_new_job(),user)
    return JsonResponse({'job':'ok'},status=200)  
        
def noset_user_work(request: HttpRequest) -> JsonResponse:
    data = json.loads(request.body)  
    
    if request.user.is_authenticated is False:
        return JsonResponse({'error':f"No authenticated"},status=500)  
    
    user = ProfileUser.get_user(request.user.id_tg) 

    job = Job.objects.filter(id=data['id_job'])
    if(job.exists() is False):
        return JsonResponse({'error':f"Not found job id:{data['id_job']}"},status=200)  
    
    set_nojob(data['id_job'],user)
    
    return JsonResponse({'nojob':'ok'},status=200)  


def nowork_user_work(request: HttpRequest) -> JsonResponse:
    data = json.loads(request.body)  
    
    if request.user.is_authenticated is False:
        return JsonResponse({'error':f"No authenticated"},status=500)  
    
    user = ProfileUser.get_user(request.user.id_tg) 

    job = Job.objects.filter(id=data['id_job'])
    if(job.exists() is False):
        return JsonResponse({'error':f"Not found job id:{data['id_job']}"},status=200)  
    job = job.first()
    job.unset_work_user()
    set_nowork_job(data['id_job'],user)
    
    return JsonResponse({'nojob':'ok'},status=200)  


def work_time_cheack(request: HttpRequest):
    jobs = Job.objects.filter(status="work")
    job =  jobs.first()
    if(job is None): 
        print(send_notification('test',job.user_job))
    for job in jobs.all():
        timeleft = job.get_timeleft_second()
        if(timeleft < 0):   
            print(send_notification(job.push_job_over(),job.user_job)) 
            set_nowork_job(job.id,job.user_job)
            job.unset_work_user()
        elif (timeleft <= 15):
            print(send_notification(f'⚠️ Осталось {timeleft} минут на выполнение задания, выполнить задание можно по ссылке: work.vvlab.space/?page=work',job.user_job))
    
    return JsonResponse('test',status=500)  

def work_complite(request: HttpRequest):
    
    if request.user.is_authenticated is False:
        return JsonResponse({'error':f"No authenticated"},status=500)  
    
    job = Job.objects.filter(id=request.POST.get('id_job'))
    if(job.exists() is False):
        return JsonResponse({'error':f"Not found job id:{str(request.POST.get('id_job'))}"},status=500)  
    job = job.first()
    
    work = job.get_active_work()
    if(work == None):
        return JsonResponse({'error':f"Not found active work for job id:{str(request.POST.get('id_job'))}"},status=500)   
    if(job.place.is_image):
        work.image = handle_uploaded_file(request.FILES['file'])
    if(job.place.is_unical):
        if(job.cheack_nickname(request.POST.get('nickname').strip())):
            return JsonResponse({'error':f"Отзыв с таким никнеймом уже выполнен."},status=500)   
    work.nickname  = request.POST.get('nickname').strip() 
    send_notification(work.push_wait_work(), request.user)
    if('text' in request.POST):
        work.text = request.POST.get('text').strip() 
    else:
        work.text = job.text
    work.save()
    job.status = 'wait_cheack' 
    job.save() 
    return JsonResponse({'status':f"Ok"},status=200)  


#Проверяется автоматически раз в день
def works_review(request: HttpRequest):
    jobs = Job.objects.filter(status="wait_cheack").all() 
    jobs_ids = []
    jobs_ids_cheack2 = []
    for  job in jobs:
        coeff = 0
        if(job.place.id == 3):
            work_active = job.get_active_work()
            coeff = cheack_review_avito(job.url,work_active.nickname,job.order.count)
        elif(job.place.id == 1):
            work_active = job.get_active_work() 
            firm = url_parse_2gis(job.url)
            coeff = cheack_review_2gis(firm,work_active.nickname,job.date_public,job.order.count)
        elif(job.place.id == 2):
            work_active = job.get_active_work() 
            firm = url_parse_flamp(job.url)
            coeff = cheack_review_2gis(firm,work_active.nickname,job.date_public,job.order.count)
        if(coeff <= 0.9):
            jobs_ids_cheack2.append(job.id)
            job.status="wait_cheack2"
        else: 
            jobs_ids.append(job.id)
            job.status="wait_pay"
        job.save()
    if(len(jobs_ids) > 0):
        text = f"💡 Отзывов проверено кол:{len(jobs_ids)} Id отзывов: {jobs_ids}"
        send_owner_notification(text)
    if(len(jobs_ids) > 0):
        text = f"💡 Отзывов отправлено на проверку кол:{len(jobs_ids_cheack2)} Id отзывов: {jobs_ids_cheack2}"
        send_owner_notification(text) 
 
    order_list = []
    for order in Order.objects.exclude(number=-1,count=0).values_list('number', 'complite'):
        order_list.append(order)
    r = requests.post('https://hm.vvlab.space/orders/update/', json={'secret_key':secret_key,'orders':order_list})  
    
    current = datetime.now().time().hour
    if(10 <= current <= 18): 
        jobs_count = Job.objects.filter(status="do",show_on_website=True,date_public__lte=datetime.now()).count() 
        if(jobs_count > 0):
            users = ProfileUser.objects.all()
            text = f'🔔 {jobs_count} новых задания, можно заработать {jobs_count*25} ₽  Выполнить: https://work.vvlab.space/'
            for user in users:
                send_notification(text,user)
    return JsonResponse({'status':f"Ok"},status=200)  



#Проверяется автоматически раз в день
def works_review_close(request: HttpRequest):
    jobs = Job.objects.filter(Q(status='wait_cheack') | Q(status='wait_cheack2') | Q(status='close')).all()
    jobs_ids = []
    count = 0 
    for  job in jobs: 
        if(job.place.id == 3):
            work_active = job.get_active_work()
            coeff = cheack_review_avito(job.url,work_active.nickname,job.order.count)
            jobs_ids.append(job.id)
            count += 1

    jobs_count = Job.objects.filter(status='close',show_on_website=True,date_public__gte=datetime.now()-timedelta(hours=24)).count()
    q_order_noworking = Order.objects.filter(date_published__lte=datetime.now()-timedelta(days=7),complite=0)
    count_order_noworking =  q_order_noworking.count()
    ids_order_noworking =  q_order_noworking.values_list('pk') 
    text = f'📊 {jobs_count} выполнено отзывов за последние 24 часа \n ❗️ {count_order_noworking} 0 отзывов выполнено за последних 7 дней ЗАКАЗЫ:{ids_order_noworking} \n 💡 Отзывов удалилось кол:{count} Id отзывов: {jobs_ids}' 
    send_owner_notification(text) 
    return JsonResponse({'status':f"Ok"},status=200)  



def work_complite_step2(request: HttpRequest): 
    if request.user.is_authenticated is False:
        return JsonResponse({'error':f"No authenticated"},status=500)  
     
    job = Job.objects.filter(id=request.POST.get('id_job'))
    if(job.exists() is False):
        return JsonResponse({'error':f"Not found job id:{str(request.POST.get('id_job'))}"},status=500)  
 
    job = job.first()
    
    work = job.get_active_work()
    if(work == None):
        return JsonResponse({'error':f"Not found active work for job id:{str(request.POST.get('id_job'))}"},status=500)   
    work.nickname = request.POST.get('nickname').strip() 
    work.image = handle_uploaded_file(request.FILES['file'])
    work.step = 2
    work.save() 
    return JsonResponse({'status':f"Ok"},status=200)  

secret_key = '559ec00b6526772cb5f8acb37c84b612'

@csrf_exempt
def public_order(request: HttpRequest):
    
    data = json.loads(request.body) 
    if(data['key'] != secret_key):
        return JsonResponse({'status':f"Нельзя"},status=200)  
    url = data['url']
    if('text' in data):
        text = data['text']
    description = ''
    if('desc' in data):
        description = data['desc'] 
    if(len(description)<3):
        description = 'Написать положительный отзыв.'
    if('count' in data):
        count = data['count'] 
    else:
        count = -1
    if('complite' in data):
        complite = data['complite'] 
    else:
        complite = 0
    status = Order.objects.create(
        number = data['id'],
        url = url_parse_create_order(url),
        description = description,
        count = count,
        complite = complite,
    )
    return JsonResponse({'status':f"Ok {status}"},status=200)  


def notifclose(request: HttpRequest): 
    if request.user.is_authenticated is False: 
        return redirect('authorize/') 
     
    job = Job.objects.filter(id=request.POST.get('id_job'))
    if(job.exists() is False):
        return JsonResponse({'error':f"Not found job id:{str(request.POST.get('id_job'))}"},status=500)  
    job = job.first()
    
    work = job.get_active_work()
    if(work == None):
        return JsonResponse({'error':f"Not found active work for job id:{str(request.POST.get('id_job'))}"},status=500)   
    work.nickname = request.POST.get('nickname').strip() 
    work.image = handle_uploaded_file(request.FILES['file'])
    work.step = 2
    work.save() 
    return JsonResponse({'status':f"Ok"},status=200)  

def error_debug(request: HttpRequest):
    
    if request.user.is_staff is False: 
        return redirect('authorize/') 
    data = json.loads(request.body) 
    
    if('error' in data): 
        send_owner_notification(f"❗️ Ошибка у клиента: {data['error']}")
    
    return JsonResponse({'status':f"Ok"},status=200)  

