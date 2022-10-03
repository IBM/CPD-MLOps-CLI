# MLOps CLI on CPD

This project includes an evolving design of the MLOps flow on CPD and the corresponding implementation as a CLI tool.

The current version covers a flow for deep learning models as the follows:
- train: code development in WS, training job on WMLA
- deploy: WMLA Elastic Distributed Inference
- monitor: custom monitor for OpenScale, headless service provider & dummy subscription, only custom monitors enabled for subscription


### Roadmap
Next steps:
- add toy model, toy data, and toy custom monitor script for dev and test
- set up unit tests
- extend to WML deployments
- extend to OOTB OpenScale monitors
- move from config yaml to factsheets host metadata shared between services


## Dependencies
Python: >= 3.8

Python packages:
- ibm-cloud-sdk-core==3.10.1
- ibm-watson-openscale>=3.0.14
- ibm-watson-machine-learning>=1.0.246
- click
- [cpd-sdk-plus](https://github.com/IBM/CPD-SDK-Plus-Python)>=1.1


## Installation
No installation needed, but you can install the dependencies as follows:
```
pip install -r requirements.txt
```

## Usage
Download the cli script and the dependency utility scripts. Now you can use it:
```
python cli_mlops.py --help
```

For example of available commands, see the [cheat sheet](cheat_sheet_cli_mlops.txt).


## How to Contribute
`DCO` is suggested to be used. See [here](https://wiki.linuxfoundation.org/dco) for details on how to do it.

## Contributors
- Rich Nieto (rich.nieto@ibm.com)
- Drew McCalmont (drewm@ibm.com)
