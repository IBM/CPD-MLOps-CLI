#!/usr/bin/env python

"""
Avoid using list() to convert a python object to a list because we re-defined list().
If needed, usse list_builtin() instead.
"""

import click
import os
import sys
import re
import yaml
import subprocess
import shutil
import json
import uuid
from ibm_watson_openscale import *
from ibm_watson_openscale.supporting_classes.enums import TargetTypes
from ibm_watson_openscale.supporting_classes.enums import *
from ibm_watson_openscale.supporting_classes import *
from ibm_watson_openscale.base_classes.watson_open_scale_v2 import *

import uuid

from cpd_sdk_plus import wml_sdk_utils as wml_util
from cpd_sdk_plus import wos_sdk_utils as wos_util
from cpd_sdk_plus import wmla_utils as wmla_util
import cpd_sdk_plus

import warnings
warnings.filterwarnings('ignore')

import pandas as pd # to format tables
pd.options.display.width = 0

USER_ACCESS_TOKEN = os.getenv('USER_ACCESS_TOKEN')
APIKEY = os.getenv('CPD_APIKEY')
USERNAME = os.getenv('CPD_USERNAME')
BASE_URL = os.getenv('CPD_BASE_URL',os.getenv('RUNTIME_ENV_APSX_URL'))
WMLA_HOST = os.getenv('WMLA_HOST')
DLIM_PATH = os.getenv('DLIM_PATH')
SPACE_ID = os.getenv('SPACE_ID')



# openscale configs
DATA_MART_ID = '00000000-0000-0000-0000-000000000000'
SUBSCRIPTION_NAME = "{DEPLOYMENT_NAME} Monitor"
FUNCTION_ASSET_NAME ='{MONITOR_NAME} Function'
FUNCTION_DEPLOYMENT_NAME = '{MONITOR_NAME} Deployment'
INTEGRATED_SYSTEM_NAME = "{MONITOR_NAME} Provider"

# metadata configs
fn_deployment_metadata = 'deployment_metadata.yml'
fn_monitor_metadata = 'monitor_metadata.yml'

global wml_client
global AUTH

# THIS SHOULD BE BASED ON CLI VERSION; FROM 2.3.7 ALL ARCH SHOULD USE REST SERVER AND USER ACCESS TOKEN FOR AUTH
# CURRENTLY IT IS A QUICK FIX FOR DLIM VERSION LOWER THAN 2.3.7
AUTH = '--rest-server {REST_SERVER} --jwt-token {USER_ACCESS_TOKEN}' if sys.platform.startswith('linux') else ''

VERSION = '1.1'

list_builtin = list

@click.group()
def cli():
    pass

@cli.command()
def version():
    click.echo(f"Current version: {color(VERSION)}")


# -------- cli group: prepare --------
@cli.group()
def prepare():
    """
    Prepare for model deployment.
    """
    pass

@prepare.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--path-yml',type=str,default='deployment_metadata.yml',help='path to the yml config file of same structure as the example config')
@click.option('--path-model',type=str,default='model/',help='path to model(s), can point to a file or a folder')
@click.option('--path-dependency',type=str,default='dependency/',help='path to dependency file(s); if you use WMLA for deployment, it needs to be a folder because you will have at least a kernel file and a readme.md to supply to WMLA')
@click.option('--force','-f',is_flag=True,help='force overwrite if assets with the same name are found')
def stage(path_yml,path_model,path_dependency,force):
    """
    Stage model files, dependency files for deployment, and yml config file into the target WML space.
    """
    path_model = path_model[:-1] if path_model.endswith('/') else path_model
    path_dependency = path_dependency[:-1] if path_dependency.endswith('/') else path_dependency
    
    # load deployment config
    conf = yaml.safe_load(open(path_yml).read())
    click.echo(f"Validating yml config {color(path_yml)}...")
    flag_valid,d_res = wml_util.metadata_yml_validate(conf,with_key=False)
    if flag_valid:
        click.echo(color('Pass','pass'))
    else:
        click.echo(f"{color('Error','error')}: structure in yml config {color(path_yml,'error')} is not valid")
        for k,v in d_res.items():
            if not v['flag_valid']:
                click.echo('\n'.join(v['msg']))
        sys.exit(1)
    
    # get final model/dependency name
    model_asset_name = os.path.basename(path_model)
    if os.path.isdir(path_model):
        model_asset_name += '.zip'
        
    dependency_asset_name = os.path.basename(path_dependency)
    if os.path.isdir(path_dependency):
        dependency_asset_name += '.zip'
        
    # upload model/dependencies
    click.echo(f'Uploading model and dependency files to WML space {color(SPACE_ID)}...')
    data_assets = wml_util.list_files(wml_client)
    
    if model_asset_name in data_assets.values() or dependency_asset_name in data_assets.values():
        if force:
            wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=True)
        else:
            value = click.prompt('Asset with same name found in the WML space. Do you want to overwrite? Type "y" to overwrite,"n" to create a new asset with the same name, empty to abort',default='',type=str)
            if value == 'y':
                wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=True)
            elif value == 'n':
                wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=False)
            elif value == '':
                click.echo(color('Aborted','error'))
                sys.exit(1)
            else:
                click.echo(f'input value {value} is not accepted')
                sys.exit(1)
    else:
        wml_util.upload_batch([path_model,path_dependency],wml_client,overwrite=False)
    
    # get model asset id
    data_assets = wml_util.list_files(wml_client,keep_only_latest=True)
    model_asset_id = [k for k,v in data_assets.items() if v == model_asset_name][0]
    
    # update yml
    conf['deployment_space_id'] = SPACE_ID
    conf['model_asset'] = model_asset_name
    conf['wmla_deployment']['dependency_filename'] = dependency_asset_name
    
    wml_util.metadata_yml_add({model_asset_id:conf},wml_client,overwrite=True)
    
    conf_loaded = wml_util.metadata_yml_load(wml_client)[model_asset_id]
    click.echo(f"Model asset id: {color(model_asset_id,'pass')}")

# -------- cli group: config --------
@cli.group()
def config():
    """
    Interact with config files.
    """
    pass

@config.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--detail',type=bool,default=False,help='whether to show details in each yml config')
def list(detail):
    data_assets = wml_util.list_files(wml_client,include_details=True,ext='.yml')
    
    if len(data_assets) == 0:
        click.echo(f"No yml config file is found in WML space {color(SPACE_ID)}")
    else:
        df_assets = pd.DataFrame.from_dict(data_assets,'index')
        print(df_assets)
        if detail:
            fns = df_assets['name'].tolist()
            for fn in fns:
                click.echo('')
                click.echo(f"**** config yml {color(fn)} ****")
                df_conf = wml_util.metadata_yml_list(wml_client,fn_meta=fn)
                click.echo(f"{color(df_conf.shape[0])} entries found")
                print(df_conf)
                click.echo('')
            
@config.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',type=str,default='',help='deployment name, the entry/entries associated with which to delete')
@click.option('--model-asset-id',type=str,default='',help='model asset id, the exact entry to delete')
def delete(name,model_asset_id):
    """
    Delete entry or entries in the deployment metadata config yml. Specify either deployment name or
    model asset id (higher priority than deployment name). 
    """
    if name == '' and model_asset_id == '':
        click.echo(f"{color('Error','error')}: Specify either --name or --model-asset-id.")
        sys.exit(1)
    
    confs = wml_util.metadata_yml_load(wml_client)
    if model_asset_id != '':
        if model_asset_id not in confs.keys():
            click.echo(f"{color('Error','error')}: model asset id {color(model_asset_id,'error')} cannot be found in the config yml.")
            sys.exit(1)
        keys_to_delete = [model_asset_id]
    else:
        keys_to_delete = [model_asset_id for model_asset_id,conf in confs.items() if conf['wmla_deployment']['deployment_name']==name]
        
    click.echo(f"{color(len(keys_to_delete))} entries to delete.")
    if len(keys_to_delete) > 0:
        wml_util.metadata_yml_delete_key(keys_to_delete,wml_client)

@config.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--path-yml',type=str,required=True,help='path to a deployment metadata yml config with one COMPLETE entry')
@click.option('--force','-f',is_flag=True,help='force overwrite if entry with same key exists')
def add(path_yml,force):
    """
    Add one or more entries into the deployment metadata yml in wml space. 
    Use this when you don't stage the model and files via the "prepare stage" command.
    Unlike the yml config pass to the "prepare stage" command, here it MUST have model asset id as the key.
    """
    metadata = yaml.safe_load(open(path_yml).read())
    
    flag_valid,d_res = wml_util.metadata_yml_validate(metadata,with_key=True)
    if flag_valid:
        click.echo(f"{color('Pass','pass')}")
        
        wml_util.metadata_yml_add(metadata,wml_client,overwrite = force)
    else:
        click.echo(f"{color('Error','error')}: not all entries are valid")
        for k,v in d_res.items():
            if not v['flag_valid']:
                if with_key:
                    click.echo(f"**** model asset id {color(k,'error')} ****")
                click.echo('\n'.join(v['msg']))
        sys.exit(1)
           
# -------- cli group: deploy --------
@cli.group()
def deploy():
    """
    Deploy staged model and files.
    """
    pass

@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name, only lowercase letters/hyphens/numbers are allowed')
@click.option('--model-asset-id',required=True,type=str,help='model asset id is used to find which model and files to deploy, along with the associated config')
@click.option('--kernel-filename',type=str,default='kernel.py',help='name of WMLA EDI kernel file')
@click.option('--custom-arg',type=str,multiple=True,help='custom key-value pairs needed for this deployment, such as username and apikey to access storage volume; for example, --custom-arg username=<my username> --custom-arg apikey=<my apikey>')
#@click.option('--dlim-path',type=str,default=None,help='path to dlim cli')
def create(name, model_asset_id, kernel_filename, custom_arg):
    """
    Deploy a model asset using associated config.
    """
    # parse custom arguments
    variables = parse_multi_arg(custom_arg)
    
    # Check validity of name
    valid_pattern = re.compile('^[a-z0-9]([-a-z0-9]*[a-z0-9])?$')
    name_check = valid_pattern.match(name)
    if name_check is None:
        raise ValueError(f"{color('Error','error')}: Deployment name {color(pair,'error')} is invalid. Only numbers, hyphens and lowercase letters are allowed.")

    
    confs = wml_util.metadata_yml_load(wml_client)
    if model_asset_id not in confs.keys():
        click.echo(f"{color('Error','error')}: model asset id {color(model_asset_id,'error')} cannot be found in config file")
        sys.exit(1)

    model_asset_ids_matched = [k for k,conf in confs.items() if conf['wmla_deployment']['deployment_name']==name]
    if len(model_asset_ids_matched) > 0:
        click.echo(f"{color('Error','error')}: deployment name {color(name,'error')} is already found in config file, associated with model asset id {color(model_asset_ids_matched[0],'error')}. Stop and delete the existing deployment before creating one with the same name.")
        sys.exit(1)
    
    conf = confs[model_asset_id]
    if conf['wmla_deployment']['deployment_name'] is not None:
        click.echo(f"{color('Error','error')}: model asset id {color(model_asset_id,'error')} is already deployed with deployment name {color(conf['wmla_deployment']['deployment_name'],'error')}. Stop and delete the existing deployment before creating one with the same model asset id.")
        sys.exit(1)
    
    click.echo(f'Deploying model asset {color(model_asset_id)} as deployment {color(name)} in WMLA...')
    
    # get information from yml
    WML_SPACE_MODEL = conf['model_asset']
    DEPLOY_DEPENDENCY_FILE = conf['wmla_deployment']['dependency_filename']

    resource_configs = conf['wmla_deployment']['resource_configs']
    KERNEL_MIN = resource_configs.get('kernel_min',1)
    KERNEL_MAX = resource_configs.get('kernel_max',3)
    KERNEL_DELAY_RELEASE_TIME = resource_configs.get('kernel_delay_release_time',60)
    TASK_EXECUTION_TIMEOUT = resource_configs.get('task_execution_timeout',60)

    ENABLE_GPUS = bool(resource_configs['enable_gpus'])
    NCPUS = resource_configs.get('n_cpus',8)
    MEM = resource_configs.get('memory_allocation',1000)
    RESOURCES = f"ncpus={NCPUS},ncpus_limit={NCPUS},mem={MEM},mem_limit={MEM}"
    
    # ---- create, update, and start deployment ----
    # 1. create temp folder
    dir_submission = f'deploy_submissions_{name}'
    if os.path.exists(dir_submission):
        shutil.rmtree(dir_submission)
    os.makedirs(dir_submission)
    
    # 2. download dependencies into temp folder
    general_dependencies = ['wmla_edi_utils.py',
                        'storage_volume_utils.py',
                        'cpd_utils.py',
                        'wml_sdk_utils.py',]
    files = general_dependencies + [DEPLOY_DEPENDENCY_FILE]
    wml_util.download_batch(files, wml_client, dir_submission)

    # 3. extract dependency file & clean up
    DEPLOY_DEPENDENCY = os.path.splitext(DEPLOY_DEPENDENCY_FILE)[0]
    shutil.unpack_archive(f"{dir_submission}/{DEPLOY_DEPENDENCY_FILE}", 
                          extract_dir=dir_submission)
    shutil.copytree(src=f"{dir_submission}/{DEPLOY_DEPENDENCY}/",
                    dst=dir_submission,
                    dirs_exist_ok=True) # param dirs_exist_ok only exists in py >= 3.8
    shutil.rmtree(f"{dir_submission}/{DEPLOY_DEPENDENCY}")
    os.remove(f"{dir_submission}/{DEPLOY_DEPENDENCY_FILE}")

    if len(custom_arg) > 0:
        wmla_util.kernel_file_prepare(f'{dir_submission}/{kernel_filename}',variables)
        print('custom arguments added:',custom_arg)
    
    # 4. create model.json accordingly
    json_content = {"name": name, 
                     "kernel_path": kernel_filename, 
                     "readme": 'README.md',
                     #"tag": "test", 
                     "weight_path": "./",  
                     "runtime": "dlipy3", 
                     "framework": "PyTorch", 
                     "schema_version": "1",
                     "mk_environments": [{'name':'WML_SPACE_ID', 'value':SPACE_ID},
                                         {'name':'WML_SPACE_MODEL', 'value':WML_SPACE_MODEL}]}

    with open(f'{dir_submission}/model.json', 'w') as f:
        json.dump(json_content, f)
    
    # 5. create deployment
    click.echo(f"Creating deployment(s) for the model...")
    print(f'{os.environ["DLIM_PATH"]} model deploy -p {dir_submission} {AUTH} -f')
    subprocess.run(f'{os.environ["DLIM_PATH"]} model deploy -p {dir_submission} {AUTH} -f',shell=True)
    
    # 6. modify deployment profile
    click.echo(f"Updating the deployment profile with specified metadata...")
    subprocess.run(f'{os.environ["DLIM_PATH"]} model viewprofile {name} -j {AUTH} > {dir_submission}/update_model.json',shell=True)

    with open(f"{dir_submission}/update_model.json",'r') as f:
        update_model = json.load(f)

    # apply changes
    update_model['policy']['kernel_min'] = KERNEL_MIN
    update_model['policy']['kernel_max'] = KERNEL_MAX
    update_model['policy']['kernel_delay_release_time'] = KERNEL_DELAY_RELEASE_TIME
    update_model['policy']['task_execution_timeout'] = TASK_EXECUTION_TIMEOUT
    update_model['resource_allocation']['kernel']['resources'] = RESOURCES
    if ENABLE_GPUS:
        update_model['kernel']['gpu'] = 'exclusive'

    # update profile
    with open(f"{dir_submission}/update_model.json",'w') as f:
        json.dump(update_model, f)
    
    subprocess.run(f'{os.environ["DLIM_PATH"]} model updateprofile {name} -f {dir_submission}/update_model.json {AUTH}',shell=True)
    
    # 7. start deployment
    click.echo(f"Starting the deployment...")
    subprocess.run(f'{os.environ["DLIM_PATH"]} model start {name} {AUTH}',shell=True)
    #edi.wait_for_model_idle_status(name,kernel_min=update_model['policy']['kernel_min'])
    
    deployment_url = f'{BASE_URL}/dlim/v1/inference/{name}'
    click.echo(f"Deploymnet url: {deployment_url}")
    
    # 8. update yml
    conf['wmla_deployment']['deployment_name'] = name
    conf['wmla_deployment']['deployment_url'] = deployment_url
    
    wml_util.metadata_yml_add({model_asset_id:conf},wml_client,overwrite=True)


@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name, only lowercase letters/hyphens/numbers are allowed')
def stop(name):
    subprocess.run(f"{os.environ['DLIM_PATH']} model stop {name} {AUTH} -f",shell=True)

@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name, only lowercase letters/hyphens/numbers are allowed')
@click.option('--remove-monitor',is_flag=True,help='a flag to remove the associated monitors in openscale')
@click.option('--remove-config',is_flag=True,help='a flag to remove the associated entry in the config yml')
def delete(name,remove_monitor,remove_config):
    res = subprocess.run(f"{os.environ['DLIM_PATH']} model undeploy {name} {AUTH} -f",shell=True)
    if res.returncode == 0:
        click.echo(f"Modifying config yml to refect this change..")
        
        if remove_monitor:
            click.echo('')
            click.echo(f"Removing the associated subscription in openscale..")
            wos_client = wos_util.get_client()
            wos_util.subscription_delete(wos_client,subscription_name=SUBSCRIPTION_NAME.format(DEPLOYMENT_NAME=name))
        
        if remove_config:
            click.echo('')
            click.echo(f"Removing the associated entry in config yml..")
            model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
            wml_util.metadata_yml_delete_key(model_asset_id,wml_client)
        else:
            click.echo('')
            click.echo(f"Removing deployment name from the associated entry in config yml...")
            model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
            if conf is None:
                click.echo(f"No config linked to deployment name {name}. The config might have been deleted already, or the deployment was not created using this cli flow.")
            else:
                conf['wmla_deployment']['deployment_name'] = None
                if remove_monitor:
                    conf['openscale_subscription_id'] = None
                wml_util.metadata_yml_add({model_asset_id:conf},wml_client,overwrite=True)
            

@deploy.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
def list():
    subprocess.run(f"{os.environ['DLIM_PATH']} model list {AUTH}",shell=True)

# -------- cli group: monitor --------
@cli.group()
def monitor():
    """
    Configure and interact with OpenScale monitors for the deployments.
    """
    pass

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name')
@click.option('--service-provider-name',type=str,default="OpenScale Headless Service Provider",help='deployment service provider configured in OpenScale')
@click.option('--no-manual-eval',type=bool,default=False,help='whether not to trigger a manual evaluation')
def create(name,service_provider_name,no_manual_eval):
    """
    Configure monitors for a deployment using the associated config.
    """
    model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
    if conf is None:
        click.echo(f"{color('Error','error')}: no config found for deployment name {color(name,'error')}")
        sys.exit(1)
    
    if conf['openscale_subscription_id'] is not None:
        click.echo(f"{color('Error','error')}: deployment {color(name,'error')} is already configured in OpenScale with subscription id {color(conf['openscale_subscription_id'],'error')}. If you want to re-configure the monitor, at the moment you need to delete the existing subscription.")
        value = click.prompt(f'Have you already deleted the existing subscription and want to proceed? Type "y" to proceed or leave it empty to abort',default='')
        if value == '':
            click.echo(color('Aborted','error'))
            sys.exit(1)
        
    print('Model asset id:',model_asset_id)
    subscription_name = SUBSCRIPTION_NAME.format(DEPLOYMENT_NAME=name)
    os.environ['MODEL_ASSET_ID'] = model_asset_id
    os.environ['WML_SPACE_ID'] = SPACE_ID
    os.environ['WOS_GUID'] = DATA_MART_ID
    
    wos_client = wos_util.get_client()
    metadata_deployment = wml_util.metadata_yml_load(wml_client,'deployment')[model_asset_id]
    metadata_monitor = wml_util.metadata_yml_load(wml_client,'monitor')
    
    
    # ---- start ----
    # 1. get subscription
    existing_providers_dict = wos_client.service_providers.list().get_result().to_dict()['service_providers']
    existing_providers = [sp['entity']['name'] for sp in existing_providers_dict]

    SERVICE_PROVIDER_ID = [sp['metadata']['id'] for sp in existing_providers_dict if sp['entity']['name'] == service_provider_name]
    if len(SERVICE_PROVIDER_ID) == 0:
        click.echo(f"{color('Error','error')}: Service provider name {color(service_provider_name,'error')} cannot be found. Check OpenScale and make sure the service provider is valid, or specify the correct service provider name.")
        sys.exit(1)
    SERVICE_PROVIDER_ID = SERVICE_PROVIDER_ID[0]
    print(f"Service provider ID: {SERVICE_PROVIDER_ID}")
    
    existing_subscriptions_dict = wos_client.subscriptions.list().get_result().to_dict()['subscriptions']
    existing_subscriptions = [sp['entity']['asset']['name'] for sp in existing_subscriptions_dict]

    if not subscription_name in existing_subscriptions:
        ASSET_ID = str(uuid.uuid4())
        ASSET_NAME = subscription_name
        url = ''

        ASSET_DEPLOYMENT_ID = str(uuid.uuid4())
        ASSET_DEPLOYMENT_NAME = subscription_name

        subscription_details = wos_client.subscriptions.add(
            data_mart_id=DATA_MART_ID,
            service_provider_id=SERVICE_PROVIDER_ID,
            asset=Asset(
                asset_id=ASSET_ID,
                name=ASSET_NAME,
                url=url,
                asset_type=AssetTypes.MODEL,
                input_data_type=InputDataType.STRUCTURED,
                problem_type=ProblemType.MULTICLASS_CLASSIFICATION
            ),
            deployment=AssetDeploymentRequest(
                deployment_id=ASSET_DEPLOYMENT_ID,
                name=ASSET_DEPLOYMENT_NAME,
                deployment_type= DeploymentTypes.ONLINE
            ),
            asset_properties=AssetPropertiesRequest(
                probability_fields=['probability']
                )
        ).result

        SUBSCRIPTION_ID = subscription_details.metadata.id
        print("Subscription ID created: {}".format(SUBSCRIPTION_ID))
    else:
        SUBSCRIPTION_ID = [sp['metadata']['id'] for sp in existing_subscriptions_dict if sp['entity']['asset']['name'] == subscription_name][0]
        print("Subscription ID found: {}".format(SUBSCRIPTION_ID))
    
    # 2. update deployment metadata
    metadata_update = {model_asset_id:{'openscale_subscription_id':SUBSCRIPTION_ID}}
    wml_util.metadata_yml_update(metadata_update,wml_client)
    metadata_deployment = wml_util.metadata_yml_load(wml_client)[model_asset_id]
    
    # 3. configure custom monitors
    metadata_deployment['openscale_custom_metric_provider'].keys()
    for monitor_id in metadata_deployment['openscale_custom_metric_provider'].keys():
        print('*'*20,'checking',monitor_id,'*'*20)
        print(wos_util.get_monitor_instance(monitor_id,SUBSCRIPTION_ID,wos_client))
    
    custom_metrics_wait_time = 360 #time in seconds 
    
    for monitor_id in metadata_deployment['openscale_custom_metric_provider'].keys():
        monitor_instance_details = wos_util.monitor_instance_create(monitor_id,
                                                                    metadata_deployment,
                                                                    metadata_monitor,
                                                                    custom_metrics_wait_time,
                                                                    wos_client)
        print(monitor_instance_details)
    
    if not no_manual_eval:
        from pprint import pprint

        subscription_id = SUBSCRIPTION_ID
        for monitor_id in metadata_deployment['openscale_custom_metric_provider'].keys():
            print('*'*30,monitor_id,'*'*30)
            parameters = {
                "custom_metrics_provider_id": metadata_monitor[monitor_id]['integrated_system_id'],
                "custom_metrics_wait_time":   custom_metrics_wait_time,
                "run_details": {
                "run_id": str(uuid.uuid4()),
                "run_status": "Running"
                }
            }

            payload= {
                "data_mart_id" : DATA_MART_ID,
                "subscription_id" : subscription_id,
                "custom_monitor_id" : monitor_id,
                "custom_monitor_instance_id" : wos_util.get_monitor_instance(monitor_id,subscription_id,wos_client)['metadata']['id'],
                "custom_monitor_instance_params": parameters

            }

            input_data= { "input_data": [ { "values": payload } ]
                        }
            job_details = wml_client.deployments.score(metadata_monitor[monitor_id]['wml_deployment_id'], input_data)
            pprint(job_details)
    

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name')
def delete(name):
    """
    Delete the monitors associated with a deployment. It essentially deletes the openscale subscription.
    """
    wos_client = wos_util.get_client()
    wos_util.subscription_delete(wos_client,subscription_name=SUBSCRIPTION_NAME.format(DEPLOYMENT_NAME=name))

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
def list():
    """
    List monitors configured for deployments.
    """
    wos_client = wos_util.get_client()
    subscriptions = wos_client.subscriptions.list().result.to_dict()['subscriptions']
    click.echo(f"{color(len(subscriptions))} subscriptions found")
    click.echo('')
    if len(subscriptions) > 0:
        df_subscriptions = pd.json_normalize(subscriptions)[['entity.asset.name',
                                                              'metadata.created_at','metadata.created_by','metadata.id']]
        df_subscriptions.columns = ['subscription_name','created_at','created_by','subscription_id']
        df_subscriptions['created_at'] = df_subscriptions['created_at'].apply(lambda x: x.split('.')[0]) 
        df_subscriptions = df_subscriptions.sort_values('created_at',ascending=False).set_index('subscription_id')
        
        monitor_instances = wos_client.monitor_instances.list().result.to_dict()['monitor_instances']
        df_monitor_instances = pd.json_normalize(monitor_instances)[['entity.target.target_id','entity.monitor_definition_id']]
        df_monitor_instances.columns = ['subscription_id','monitor']
        df_monitor_instances = df_monitor_instances.groupby('subscription_id').agg(list_builtin)
        df_monitor_instances['monitor'] = df_monitor_instances['monitor'].apply(lambda x: ', '.join(x))
        
        print(df_subscriptions.join(df_monitor_instances,how='left'))

@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='deployment name')
def status(name):
    """
    Check monitor status. Basically it queries the evaluation results of the most recent run.
    """
    wos_client = wos_util.get_client()
    
    model_asset_id, conf = get_metadata_by_deployment_name(name,wml_client)
    if conf is None:
        click.echo(f"{color('Error','error')}: no config found for deployment name {color(name,'error')}")
        sys.exit(1)
    
    if conf['openscale_subscription_id'] is None:
        click.echo(f"{color('Error','error')}: Config for deployment {color(name,'error')} does not have a subsription id. Have you configured the monitors?")
        sys.exit(1)
    
    click.echo(f'Fetching latest monitor status for deployment {color(name)} (model asset id {color(model_asset_id)})...')
    subscription_id = conf['openscale_subscription_id']
    for monitor_id in conf['openscale_custom_metric_provider'].keys():
        l_measurements = wos_client.monitor_instances.measurements.query(target_id=subscription_id,
                                                                        target_type=TargetTypes.SUBSCRIPTION,
                                                                        monitor_definition_id=monitor_id,
                                                                        recent_count=1).result.to_dict()['measurements']
        if len(l_measurements) == 0:
            click.echo(f'Monitor {color(monitor_id)} does not have any evaluation run yet.')
        else:
            measurements = l_measurements[0]
#             thresholds = conf['openscale_custom_metric_provider'][monitor_id]['thresholds']
            click.echo('')
            click.echo(f"**** Monitor {color(monitor_id)}:")
            click.echo(f"measurement id: {color(measurements['metadata']['id'])}")
            click.echo(f"evaluation run id: {color(measurements['entity']['run_id'])}")
            click.echo(f"evaluation run started at: {color(measurements['entity']['timestamp'])}")
            
            count_issue = measurements['entity']['issue_count']
            click.echo(f"{color(count_issue,'pass') if count_issue == 0 else color(count_issue,'error')} metric(s) violating the threshold.")
            if count_issue > 0:
                metrics = measurements['entity']['values'][0]['metrics']
                
                d_metrics_id2name = wos_util.get_monitor_metrics(monitor_id,wos_client,key='id')
                metrics = sorted(metrics,key=lambda d:d_metrics_id2name[d['id']])
                
                for metric in metrics:
                    try:
                        if metric['value'] < metric['lower_limit']:
                            click.echo(f"{color(d_metrics_id2name[metric['id']],'warning')}: value {color(round(metric['value'],4),'warning')} lower than threshold {color(metric['lower_limit'],'warning')}")
                    except:
                        pass
                    
                    try:
                        if metric['value'] > metric['upper_limit']:
                            click.echo(f"{color(d_metrics_id2name[metric['id']],'warning')}: value {color(round(metric['value'],4),'warning')} higher than threshold {color(metric['upper_limit'],'warning')}")
                    except:
                        pass



@monitor.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
@click.option('--name',required=True,type=str,help='monitor template name')
@click.option('--path-script',required=True,type=str,help='path to the custom monitor script')
@click.option('--path-metadata',required=True,type=str,help='path to the metadata yml for the custom monitor')
@click.option('--custom-arg',type=str,multiple=True,help='custom key-value pairs needed for deploying this script as REST API, such as username and apikey to access storage volume; for example, --custom-arg username=<my username> --custom-arg apikey=<my apikey>')
@click.option('--auth-arg',required=True,type=str,multiple=True,help='authroization key-value pairs needed for OpenScale to call the deployed script; more specifically, you MUST specify --auth-arg CPD_USERNAME=<my username> --auth-arg CPD_API_KEY=<my apikey>')
@click.option('--software-spec',default='runtime-22.1-py3.9',type=str,help='software specification in WML used for the monitor as a rest API')
def register(name, path_script, path_metadata, custom_arg, auth_arg, software_spec):
    """
    Register a new custom monitor "template" in OpenScale that can later on be further configured and used by
    any number of subscriptions.
    
    THIS IS A NEW METHOD NOT FULLY TESTED AND NOT DOCUMENTED.
    """
    conf = yaml.safe_load(open(path_metadata).read())

    # 0. parse custom and authorization arguments
    if len(custom_arg) > 0:
        path_script = wml_util.script_prepare(path_script,parse_multi_arg(custom_arg),overwrite=False)
        click.echo(f"custom arguments added:{custom_arg}")
    
    auth_arg = parse_multi_arg(auth_arg)

    # 1. create a function in WML space with the given script
    # TODO: SOFTWARE SPEC BASED ON CPD VERSON
    function_asset_id = wml_util.function_store(path_script,wml_client, function_name=FUNCTION_ASSET_NAME.format(MONITOR_NAME=name),
                                                software_spec=software_spec)
    click.echo(f"Function asset created, id: {color(function_asset_id)}")

    # 2. create the deployment for this function
    deployment_id,scoring_url = wml_util.function_deploy(function_asset_id,wml_client, function_deployment_name=FUNCTION_DEPLOYMENT_NAME.format(MONITOR_NAME=name))
    click.echo(f"Deployment created, id: {color(deployment_id)}, url: {color(scoring_url)}")

    # 3. parse credentials from the script
    wos_client = wos_util.get_client()
    # Delete existing custom metrics provider integrated systems if present
    wos_util.integrated_system_delete(INTEGRATED_SYSTEM_NAME.format(MONITOR_NAME=name),wos_client)
    
    # 4. register the deployment as an integrated system in openscale
    custom_metrics_integrated_system = IntegratedSystems(wos_client).add(
            name=INTEGRATED_SYSTEM_NAME.format(MONITOR_NAME=name),
            description=INTEGRATED_SYSTEM_NAME.format(MONITOR_NAME=name),
            type="custom_metrics_provider",
            credentials= {"auth_type":"bearer",
                        "token_info": {
                            "url": "{}/icp4d-api/v1/authorize".format(os.environ['BASE_URL']),
                            "headers": {"Content-Type": "application/json",
                                        "Accept": "application/json"},
                            "payload": {'username':auth_arg['CPD_USERNAME'],
                                        'api_key':auth_arg['CPD_API_KEY']},
                            "method": "post"}
                        },
            connection={"display_name": INTEGRATED_SYSTEM_NAME.format(MONITOR_NAME=name),
                        "endpoint": scoring_url
            }).result

    integrated_system_id = custom_metrics_integrated_system.metadata.id
    click.echo(f"Integrated system created, id: {color(integrated_system_id)}")

    # 5. register custom monitor in openscale
    monitor_id = wos_util.monitor_definition_create(name,
                                                    conf['thresholds'],
                                                    wos_client,overwrite=True)
    click.echo(f"Monitor created, id: {color(monitor_id)}")

    metadata = {monitor_id:
            {'integrated_system_id':integrated_system_id,
             'wml_deployment_id':deployment_id}}

    # 6. register the newly added monitor into the metadata file
    wml_util.metadata_yml_add(metadata,wml_client,metadata_type='monitor',overwrite=True)
    print(wml_util.metadata_yml_load(wml_client,metadata_type='monitor'))

# -------- util --------
    
def get_metadata_by_deployment_name(name,wml_client):
    model_asset_id = None
    conf = None
    
    confs = wml_util.metadata_yml_load(wml_client)
    for k,v in confs.items():
        try:
            if v['wmla_deployment']['deployment_name']==name:
                model_asset_id = k
                conf = v
        except:
            pass
    
    return model_asset_id, conf

def parse_multi_arg(args):
    variables = {}
    for pair in args:
        pair_parsed = pair.split('=')
        if len(pair_parsed) != 2:
            click.echo(f"{color('Error','error')}: Key-value pair {color(pair,'error')} not have exactly 1 equal sign")
            sys.exit(1)
        k = pair_parsed[0]
        v = pair_parsed[1]
        if len(k) == 0 or v == 0:
            click.echo(f"{color('Error','error')}: Key-value pair {color(pair,'error')} has an invalid key or value")
            sys.exit(1)
        variables[k] = v
    return variables

def color(x,condition='normal'):
    if condition=='normal':
        return click.style(str(x),fg='blue')
    elif condition=='error':
        return click.style(str(x),fg='red')
    elif condition=='warning':
        return click.style(str(x),fg='yellow')
    elif condition=='pass':
        return click.style(str(x),fg='green')
    else:
        raise Exception(f'condition {condition} not supported')

if __name__ == '__main__':
    # validate host
    if BASE_URL is None:
        click.echo(f"\nConfigure {color('CPD base url')} by exporting it as environment variable CPD_BASE_URL")
        sys.exit(1)
    
    if WMLA_HOST is None:
        click.echo(f"\nConfigure {color('WMLA host url')} by exporting it as environment variable WMLA_HOST")
        sys.exit(1)
    REST_SERVER = WMLA_HOST + '/dlim/v1/'

    # validate credentials
    if USER_ACCESS_TOKEN is None:
        if APIKEY is None or USERNAME is None:
            click.echo(f"\nConfigure {color('user access token')}, or {color('username')} AND {color('apikey')}, by exporting the info as environmet variable USER_ACCESS_TOKEN (or CPD_USERNAME and CPD_APIKEY). To get a token, refer to https://cloud.ibm.com/apidocs/cloud-pak-data#getauthorizationtoken or use the \"get_access_token()\" method in cpd_utils.py.")
            sys.exit(1)
        os.environ['USER_ACCESS_TOKEN'] = cpd_sdk_plus.get_access_token({'username':USERNAME,'api_key':APIKEY})
        print(os.environ['USER_ACCESS_TOKEN'])
    
    # validate wml space id
    if SPACE_ID is None:
        click.echo(f"\nConfigure {color('wml space id')} (the target space you want to stage model files and dependencies) by exporting it as an environment variable SPACE_ID. In terminal, you can do \"export SPACE_ID=<id>\"; in python, you can do \"os.environ['SPACE_ID']=<id>\".")
        sys.exit(1)

    # validate dlim
    if DLIM_PATH is None:
        env_paths = os.environ['PATH'].split(':')#[os.environ['HOME']+'/bin', '/userfs']
        dlim_paths = []
        for env_path in env_paths:
            if env_path is not None:
                if not os.path.isfile(env_path):
                    dlim_paths += [env_path + '/dlim', env_path + '/dlim-darwin', env_path + '/dlim.exe']
                else:    
                    dlim_paths.append(env_path)

        for path in dlim_paths:
            if os.path.exists(path):
                if not os.access(path, os.X_OK):
                    raise Exception("dlim program not executable...check permissions")
                os.environ['DLIM_PATH'] = path
                break
        
        # if the env var DLIM_PATH is still not filled
        DLIM_PATH = os.getenv('DLIM_PATH')
        if DLIM_PATH is None:
            click.echo(f'\nCannot find executable {color("dlim")}. Make sure the path to your dlim file (e.g., ./dlim-linux) is included in $PATH and the file is executable. You can do this by running "export PATH=$PATH:<path to my dlim file>", or move the dlim file to a folder already added to $PATH while keeping the filename as "dlim". To make dlim executable, consider command "chmod +x dlim" or "chmod 755 dlim".')
            value = click.prompt('If you do not have the dlim file in place, do you want to download it now?',default='',type=str)
            if value == 'y':
                if sys.platform == 'darwin':
                    operation_system = 'mac'
                    filename = 'dlim-darwin'
                elif sys.platform.startswith('linux'):
                    operation_system = 'linux'
                    filename = 'dlim'
                elif sys.platform.startswith('win'):
                    operation_system = 'windows'
                    dilename = 'dlim.exe'
                else:
                    click.echo(f"Your operation system detected by python is {color('sys.platform','error')}. It may not be supported.")
                    sys.exit(1)
                wmla_util.download_cli(service='dlim',operation_system=operation_system,rest_host=WMLA_HOST)
                subprocess.run(f'chmod +x {filename}',shell=True)
                os.environ['DLIM_PATH'] = filename
                if sys.platform == 'darwin':
                    subprocess.run(f"{os.environ['DLIM_PATH']} config -c {WMLA_HOST+'/dlim/v1/'}",shell=True)
                    click.echo('Run the following command to configure the cli, and then you can re-run your mlops command: dlim-darwin config -t -u <username> -x <password>')
                    sys.exit(1)
            else:
                click.echo(color('Aborted','error'))
                sys.exit(1)
    
    click.echo(f"Detected authorization info. \nYou are working with WML space {color(SPACE_ID)}.\nLocation of executable cli {color('dlim')}: {color(DLIM_PATH)}")
    click.echo('')
    
    # validate if metadata files exist
    click.echo(f"Checking presence of deployment metadata {fn_deployment_metadata} and monitor metadata {fn_monitor_metadata}...")
    wml_client = wml_util.get_client(space_id=SPACE_ID)
    l_asset_names = wml_util.list_files(wml_client).values()
    for fn in [fn_deployment_metadata, fn_monitor_metadata]:
        if fn not in l_asset_names:
            click.echo(f"{color('Error','error')}: yml config {color(fn,'error')} cannot be found")
            sys.exit(1)
    
    AUTH = AUTH.format(REST_SERVER=REST_SERVER, USER_ACCESS_TOKEN=USER_ACCESS_TOKEN)
    
    cli()
