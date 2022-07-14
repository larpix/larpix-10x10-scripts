Please refer to the charge acceptance testing documentation for the most up to date instructions: https://docs.google.com/document/d/1xePnbIQYTACgnkbCunTGQitOliaqGP7bb6tcuGjYnOI/edit?usp=sharing


## For users

The larpix-control software is a prerequisite. To get the latest tagged version:
```
pip3 install larpix-control
```
To get a tagged version of the QC test scripts contained in this repository:
```
git clone -b v1.0.1 https://github.com/larpix/larpix-10x10-scripts.git
```
## For developers

Development for the next tag happens in a branch named devel_vX.Y.Z
This branch will eventually be tagged as vX.Y.Z pulled into main.
For example, after tagging v.1.0.1:
```
git clone -b v1.0.1 git@github.com:larpix/larpix-10x10-scripts.git
cd larpix-10x10-scripts
git checkout -b devel_v1.0.2
<make edtis, git add, git commit>
git push -u origin devel_v1.0.2
```
Developers can continue to push to this branch until it is ready to be validated and tagged.
