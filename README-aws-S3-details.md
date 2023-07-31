# Terraform S3 backend details (under the hood)
For completeness we will describe the S3 backend here.

The provisioning system uses a S3 bucket for various requirements.
* To provide a global backend for terraform workspaces
* To store the terraform files needed to deploy the sliderule server software

Along with the provisioning system SlideRule consists of the following cloud applications:
- The provisioning system (i.e. prov-sys which has a web frontend at ps.slideruleearth.io)
    - prov-sys deploys a cluster for each organization using a cluster terraform configuration
- The main sliderule website (i.e. static-website which is slideruleearth.io)
- The sliderule demo website (i.e. demo)
- The sliderule server clusters deployed by the provisioning system, one for each organization supported

Each of these applications have their own configuration for their independent terraform instantiations. The provisioning system deploys a seperate instatiation of the sliderule server cluster for each organization

The sliderule provisioning system can be deployed to multiple domains simultaneously to facilitate testing and CI/CD development. Each of these seperate provisioning systems can deploy clusters for various organizations. Terraform stores the state of these seperate instatiations of infrustructre globally in a shared "backend" system. The Sliderule terraform backend will be "S3" (i.e. amazon S3). See https://www.terraform.io/language/settings/backends/s3 for more terraform specific details.

Terraform S3 backend configuration deliberately prevents variable or named values used in the definition. With that limitation in mind the following backend hierarchy was chosen.

With two domains:
- slideruleearth.io
- testsliderule.org

And the following applications:
 - cluster  (with these orgs)
    - sliderule
    - developers
    - \<org\>
- demo
- prov-sys
- static-website

Using this following pattern to namespace the workspaces.
\<domain\>-\<app\>[-\<org\>] and the following pattern for each applications' terraform backend configuration will produce the heirarchy shown below.

```
terraform {
  backend "s3" {
    bucket  = "sliderule"
    key     = "tf-states/<app>.tfstate"
    workspace_key_prefix = "tf-workspaces"
    encrypt = true
    profile = "default"
    region  = "us-west-2"
  }
}
```
## S3 Hierarchy:

```
sliderule   (<--------- this is an S3 bucket)
│
└───config
│   │   
│   └───<files>   
│     
└───infrastructure
│   │   
│   └───software
│   │   │   
│   |   └─── <ec2 terraform packer files> 
│   │   
└───prov-sys
│   │   
│   └───cluster_tf_versions
│   │   │   
│   |   └───V2 
│   │   │   └─── <cluster terraform files> 
│   │   │   
│   |   └─── V2.0.0 
│   │      └─── <cluster terraform files> 
│   │
└───tf-workspaces
│   │   
│   └───slideruleearth.io-demo   
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───slideruleearth.io-cluster-sliderule
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───slideruleearth.io-cluster-developers  
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───slideruleearth.io-cluster-<org>  
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───slideruleearth.io-prov-sys   
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───prov-sys.tfstate
│   │   
│   └───slideruleearth.io-static-website   
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───static-website.tfstate
│   │ 
│   └───testsliderule.org-demo   
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───demo.tfstate
│   │   
│   └───testsliderule.org-cluster-sliderule
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───testsliderule.org-cluster-developers  
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───testsliderule.org-cluster-<org>  
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───cluster.tfstate
│   │   
│   └───testsliderule.org-prov-sys   
│   │   │   
│   │   └───tf-states   
│   │       │   
│   │       └───prov-sys.tfstate
│   │   
│   └───testsliderule.org-static-website   
│       │   
│       └───tf-states   
│           │   
│           └───static-website.tfstate
│
│
└───tf-states  (<-- where the default workspaces reside)
    │
    └───demo.tfstate
    └───developers.tfstate
    └───cluster.tfstate
    └───prov-sys.tfstate
    └───sliderule.tfstate
    └───static-website.tfstate
```
