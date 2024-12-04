import glob
import numpy as np
from PIL import Image
import py360convert
import numpy as np
import os
from PIL import Image
import glob
import yaml

sides = ['left', 'front', 'right', 'back']

with open('config.yaml') as f:
    config = yaml.safe_load(f)
    size = config['projected_resolution']
    available_sides = [config['sides'][n] for n in sides]

def project_panoramas(filename):
    cube_dice = np.array(Image.open(filename))
    cube_h = py360convert.e2c(cube_dice, face_w=size)
    imgs = [cube_h[size:size*2,n*size:(n+1)*size,:] for n in range(4)]
    
    for i, img in enumerate(imgs):
        if available_sides[i]:
            pimg = Image.fromarray(img)
            lat_long = "_".join(filename[10:].split('_')[:2])
            pimg.save(os.path.join('cube_pano', "%s%s%s.%s"%(lat_long,'_',sides[i],'.jpg')))


if __name__ == "__main__":
    panoramas = glob.glob('panoramas/*.jpg')

    print(f"Loaded {len(panoramas)} panoramas")

    if not os.path.isdir('cube_pano'):
        os.makedirs("cube_pano")

    for pano in panoramas:
        project_panoramas(pano)

    print(f"Finished projecting panoramas")