from __future__ import absolute_import
# though cupy is not used but without this line, it raise errors...
import cupy as cp
import os

import ipdb
import matplotlib
from tqdm import tqdm

from utils.config import opt
from data.dataset import Dataset, TestDataset, inverse_normalize
from model.point_linking_inceptionresnetv2 import PointLinkInception

from torch.utils import data as data_
from trainer import PointLinkTrainer
from utils import array_tool as at
from utils.vis_tool import visdom_bbox, vis_image
from utils.eval_tool import eval_detection_voc

# fix for ulimit
# https://github.com/pytorch/pytorch/issues/973#issuecomment-346405667
import resource

rlimit = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (20480, rlimit[1]))

matplotlib.use('agg')


def eval(dataloader, point_link, test_num=1000):
    pred_bboxes, pred_labels, pred_scores = list(), list(), list()
    gt_bboxes, gt_labels, gt_difficults = list(), list(), list()
    for ii, (imgs, sizes, gt_bboxes_, gt_labels_, gt_difficults_) in tqdm(enumerate(dataloader)):
        sizes = [sizes[0][0].item(), sizes[1][0].item()]
        pred_bboxes_, pred_labels_, pred_scores_ = point_link.predict(imgs, [sizes])
        gt_bboxes += list(gt_bboxes_.numpy())
        gt_labels += list(gt_labels_.numpy())
        gt_difficults += list(gt_difficults_.numpy())
        pred_bboxes += pred_bboxes_
        pred_labels += pred_labels_
        pred_scores += pred_scores_
        if ii == test_num: break
    result = eval_detection_voc(
        pred_bboxes, pred_labels, pred_scores,
        gt_bboxes, gt_labels, gt_difficults,
        use_07_metric=True)
    return result

def train(**kwargs):
    opt._parse(kwargs)
    print("======!!========")
    print(kwargs)
    dataset = Dataset(opt)
    print('load data')
    dataloader = data_.DataLoader(dataset, \
                                  batch_size=1, \
                                  shuffle=False, \
                                  # pin_memory=True,
                                  num_workers=opt.num_workers)
    testset = TestDataset(opt)
    test_dataloader = data_.DataLoader(testset,
                                       batch_size=1,
                                       num_workers=opt.test_num_workers,
                                       shuffle=False, \
                                       pin_memory=True
                                       )
    point_link = PointLinkInception()
    print('model construct completed')
    trainer = PointLinkTrainer(point_link).cuda()
    if opt.load_path:
        trainer.load(opt.load_path)
        print('load pretrained model from %s' % opt.load_path)
    trainer.vis.text(dataset.db.label_names, win='labels')
    best_map = 0
    lr_ = opt.lr
    #print("begin epoch ============================")
    for epoch in range(opt.epoch):
        trainer.reset_meters()
        #print("shape of dataloader", len(dataloader))
        #print(tqdm)
        for ii, (img, bbox_, label_, scale) in tqdm(enumerate(dataloader)):
            #print("before scalar")
            scale = at.scalar(scale)
            img, bbox, label = img.cuda().float(), bbox_.cuda(), label_.cuda()
            #print("bbox before train_step", bbox.shape, bbox)
            trainer.train_step(img, bbox, label)
            if (ii + 1) % opt.plot_every == 0:
                if os.path.exists(opt.debug_file):
                    ipdb.set_trace()

                # plot loss 
                #print("meter", trainer.get_meter_data())
                trainer.vis.plot_many(trainer.get_meter_data())
                # plot groud truth bboxes
                ori_img_ = inverse_normalize(at.tonumpy(img[0]))
                gt_img = visdom_bbox(ori_img_,
                                     at.tonumpy(bbox_[0]),
                                     at.tonumpy(label_[0]))
                trainer.vis.img('gt_img', gt_img)
                # plot predicti bboxes
                _bboxes, _labels, _scores = trainer.point_link.predict_center_offset_and_exist([ori_img_], visualize=True)
                if _bboxes is not None:
                    pred_img = visdom_bbox(ori_img_,
                                       at.tonumpy(_bboxes[0]),
                                       at.tonumpy(_labels[0]),
                                       at.tonumpy(_scores[0]))
                else:
                    pred_img = vis_image(ori_img_)
                trainer.vis.img('pred_img', pred_img)
        '''print("begin eval")
        eval_result = eval(test_dataloader, point_link, test_num=60)
        trainer.vis.plot('test_map', eval_result['map'])
        lr_ = trainer.point_link.optimizer.param_groups[0]['lr']
        log_info = 'lr:{}, map:{},loss:{}'.format(str(lr_),
                                                  str(eval_result['map']),
                                                  str(trainer.get_meter_data()))
        trainer.vis.log(log_info)
        print("==========epoch==========")
        print(epoch)
        print("=========eval_result['map']==========")
        print(eval_result['map'])
        print("=========best_map=========")
        print(best_map) 
        if eval_result['map'] >= best_map:
            best_map = eval_result['map']
            best_path = trainer.save(best_map=best_map)
        if epoch == 4:
            trainer.load(best_path)
            trainer.point_link.scale_lr(opt.lr_decay)
            lr_ = lr_ * opt.lr_decay'''
        trainer.save({"epoch": epoch})
        if epoch == 13:
            break
        
        #trainer.vis.plot({"eval_center": point_link.eval_center(test_dataloader).float()})
        print(epoch)

if __name__ == '__main__':
    import fire

    fire.Fire()
