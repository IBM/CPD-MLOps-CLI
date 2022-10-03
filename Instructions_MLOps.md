# Instructions for MLOps

This MLOps flow starts from the stage when researchers / data scientists finished training the model and testing the deployment, and shared their model file(s), deployment script, and configurations for deployment & monitor to the MLOps team.

## 1. Preparation
Make sure the researchers / data scientists provided the following items before you can proceed:
- [ ] Model file(s), a folder or a file
- [ ] Deployment folder, including:
  - [ ] Main deployment script a.k.a. kernel file
  - [ ] Readme.md (if there is not, you can create one; it's required by WMLA EDI but has no impact)
  - [ ] (Optional) Other dependencies
- [ ] Deployment settings, including:
  - [ ] Deployment name
  - [ ] Resources config, for example:
```
{'enable_gpus':'True',
 'n_cpus':8,
 'memory_allocation':10000,
 'n_replicas':1,
 'n_min_kernels':1,
 'task_execution_timeout':2*60}
```

- [ ] Monitor settings, including:
  - [ ] Monitor name / id
  - [ ] Monitor configuration
    - [ ] (Optional) Information needed by specific monitor
    - [ ] Thresholds, for example:
```
THRESHOLDS = {'metric1': {'threshold': [60.0, 'lower']},
 'metric2': {'threshold': [0.6, 'lower']}}
```

You may refer to the example yaml [deployment_metadata_cli_example.yml]() and ask researchers / data scientists to provide you with a deployment metadata yaml of the same structure. The CLI tool checks the structure of the provided yaml.

#### How to make my yaml based on the example?
You can create a copy of the example and make modifications.
- ignore the fields with null value as they will be filled automatically during the MLOps process
- ignore the main key "MODEL_ASSET_ID" - yes it will be auto-filled too :)
- mainly what needs to be configured are:
  1. deployment configuration, such as how much memory is needed, etc.
  2. monitor configuration, such as the threshold for each metric under each monitor
    - you need to delete the unwanted monitor from the example and add your preferred one(s) if they are not already there
    - refer to [section 3.3]() to see how to get all metrics and their default thresholds
    

## 2. Procedures

### 2.1 Prepare the environment
If you run from a Watson Studio environment on the cluster where you intend to deploy the model, you need to provide the following information:
```
export WMLA_HOST=https://wmla-console-*****
export PATH=$PATH:****
export SPACE_ID=*****
```

- WMLA_HOST: the link to your WMLA console (NO SLASH AT THE END OF STRING)
- PATH: path to your dlim tool if you have already downloaded it, otherwise the CLI tool will download it for you
- SPACE_ID: the WML deployment space id to stage the deployment-related files

If you do not use such an environment but run from for example your local laptop, you need to in addition tell where the cluster is and how to authenticate:
```
export CPD_BASE_URL=https://*****
export CPD_USERNAME=******
export CPD_APIKEY=******
```
- CPD_BASE_URL: the link to your CPD cluster (NO SLASH AT THE END OF STRING)
- CPD_USERNAME: the username
- CPD_APIKEY: the apikey


#### How to get CPD APIKEY?
To get an APIKEY, refer to [this doc page](https://www.ibm.com/docs/en/cloud-paks/cp-data/4.5.x?topic=steps-generating-api-keys#api-keys__platform).

### 2.2 Stage the model and dependency files, along with the config
You will see model asset id printed out that you may need for steps afterwards..
```
python cli_mlops.py prepare stage --path-model=**** --path-dependency=**** --path-yml=/userfs/deployment_metadata_cli_example.yml
```

### 2.3 Deploy the model

```
python cli_mlops.py deploy create --name test --model-asset-id **** --kernel-filename kernel.py
```

Optionally, you can provide user-defined variables which will be **inserted** into the kernel file (which defines the api logic) using the `--custom-arg` argument. For example:
```
python cli_mlops.py deploy create --name test --model-asset-id **** --kernel-filename kernel.py --custom-arg CPD_USERNAME=**** --custom-arg CPD_API_KEY=******** --custom-arg VOLUME_DISPLAY_NAME=**** --custom-arg CPD_BASE_URL=https://****
```
This creates 4 lines at the beginning of the duplicated kernel file:
```
CPD_USERNAME=****
CPD_API_KEY=********
VOLUME_DISPLAY_NAME=****
CPD_BASE_URL=https://****
```
This argument is useful when you only want to add deployment-specific information on the fly, such as credentials, which is not supposed to be included in the script and be versioned & memorized in a git system.

### 2.4 Configure monitors for the model
Note that the deployment name is already specified (actually updated) in the yaml file which is done by the `deploy create` command. When you mention a deployment name here, the CLI tool will look up the deployment metadata, find out the corresponding model asset, configurations, deployment id etc., and create the monitors as instructed by the yaml file.
```
python cli_mlops.py monitor create --name ****
```

### 2.5 Check the latest evaluation result of the monitors
This method retrieves the information of the latest evaluation for each of the monitors configured with your deployment.
```
python cli_mlops.py monitor status --name ****
```

### 2.6 Delete deployment
To delete a deployment, it technically can involve deleting i) the deployment itself, ii) the associated monitors, and iii) the information in the centralized yaml file.

```
python cli_mlops.py deploy stop --name ****

python cli_mlops.py deploy delete --name ****

python cli_mlops.py monitor delete --name ****

python cli_mlops.py config delete --name ****
```

The last three can be combined into one command:
```
python cli_mlops.py deploy delete --name **** --remove-monitor --remove-config
```

### 2.6 Others
A few other commands that might be of interest are:
```
# list some information
python cli_mlops.py monitor list
python cli_mlops.py deploy list
python cli_mlops.py config list
python cli_mlops.py config list --detail True

# add a config yaml separately
python cli_mlops.py config add --path-yml deployment_metadata_cli_example2.yml

# delete a config yaml from the centralized one
python cli_mlops.py config delete --model-asset-id ****
python cli_mlops.py config delete --name ****

# check the version of the tool
python cli_mlops.py version
```

## 3. User Configuration
Here lists a few tricky fields to find a value for:

### 3.1 `WML_SPACE_ID`: WML Deployment Space ID
You need to first decide which WML deployment space to use so you know the name of it. Then, you can find the space id either from the UI (Deployments -> <your deployment space> -> Manage -> General -> Space GUID), or programmatically as the follows:
```
from cpd_sdk_plus import wml_sdk_utils as wml_util
wml_client = wml_util.get_client()
wml_client.spaces.list(limit=100)
```

### 3.2 `SERVICE_PROVIDER_NAME`: Deployment Provider in OpenScale Monitor
For WMLA deployments, you can use a headless provider for OpenScale, meaning that it provides dummy information and is not technically linked to a real service that handles deployments. 

This is because 
1. WMLA is not an out-of-the-box deployment provider supported in OpenScale
2. The custom monitors we support at the moment are supposed to get the ground truth data & predicted data from a CPD storage volume, and hence do **not** require OpenScale to interact with a deployment endpoint.

You can view all the available deployment provider already registered in OpenScale, and get the name of the provider you wish to use:
```
from cpd_sdk_plus import wos_sdk_utils as wos_util
wos_client = wos_util.get_client()
wos_client.service_providers.show()
```

If you need to create a new headless deployment provider, follow notebook [C1_OpenScale_Dummy_ML_Provider.ipynb]()

### 3.3 `THRESHOLDS_<>`: Metric Thresholds for OpenScale Monitor
Get default monitor thresholds:
```
from cpd_sdk_plus import wos_sdk_utils as wos_util
wos_client = wos_util.get_client()

thresholds = wos_util.get_default_thresholds('<monitor_id>',wos_client)
```

You may programmatically change the threshold of specific metric in a monitor:
```
# modify thresholds for your subscription/deployment
thresholds['metric1']['threshold'][0] = 100
thresholds['metric2']['threshold'][0] = 800
```

Or, copy and paste the output of the thresholds object (a python dictionary), and modify the values accordingly.
```
thresholds = {'metric1': {'threshold': [100, 'lower']},
              'metric2': {'threshold': [800, 'lower']}}
```
    

## 4. Fetch Monitor Status Manually
Use the following code snippet to fetch monitor status.

```
from cpd_sdk_plus import wos_sdk_utils as wos_util
wos_client = wos_util.get_client()
```

### Custom monitors
```
from ibm_watson_openscale.supporting_classes.enums import TargetTypes
wos_client.monitor_instances.measurements.query(target_id=<subscription id>,
                                                target_type=TargetTypes.SUBSCRIPTION,
                                                monitor_definition_id=<monitor id>,
                                                recent_count=1).result.to_dict()
```

### OOTB monitors
Get monitor instance id and run id:
```
wos_util.get_monitor_instance(<monitor id>,<subscription id>,wos_client)
```

Get run details:
```
wos_client.monitor_instances.get_run_details(monitor_instance_id=<monitor instance id>,
                                             monitoring_run_id=<run id>)
```

Alternatively, you can list all the runs of a monitor instance:
```
wos_client.monitor_instances.list_runs(monitor_instance_id=<monitor instance id>).result.to_dict()
```

