import React from 'react';
import moment from 'moment';
import { Modal, Form, Input, Button, DatePicker, Space } from 'antd';
import { LinkOutlined, PlusOutlined, MinusCircleOutlined } from '@ant-design/icons';

import { LinkInfo } from './LinkInfo';
import { serverValidateAlias, serverValidateLongUrl } from './Validators';
import './FixAliasRemoveButton.less';

export interface EditLinkFormValues {
    title: string;
    long_url: string;
    expiration_time: moment.Moment | null;
    aliases: { alias: string, description: string }[];
}

export interface Props {
    visible: boolean;
    userPrivileges: Set<string>;
    linkInfo: LinkInfo;
    onOk: (values: EditLinkFormValues) => void;
    onCancel: () => void;
}

export const EditLinkModal: React.FC<Props> = (props) => {
    const [form] = Form.useForm();
    const mayEditAliases = props.userPrivileges.has('power_user') || props.userPrivileges.has('admin');
    const initialValues: any = {
        ...props.linkInfo,
        expiration_time:
            props.linkInfo.expiration_time === null ? null : moment(props.linkInfo.expiration_time),
        aliases: props.linkInfo.aliases.filter(alias => !alias.deleted),
    };

    return (
        <Modal
            visible={props.visible}
            title='Edit link'
            onOk={() => {
                form
                    .validateFields()
                    .then(values => {
                        form.resetFields();
                        props.onOk(values as EditLinkFormValues);
                    });
            }}
            onCancel={() => { form.resetFields(); props.onCancel(); }}>
            <Form form={form} layout={'vertical'} initialValues={initialValues}>
                <Form.Item
                    label="Title"
                    name="title"
                    rules={[{ required: true, message: 'Please input a title.' }]}>
                    <Input placeholder="Title" />
                </Form.Item>

                <Form.Item
                    label="Long URL"
                    name="long_url"
                    rules={[
                        { required: true, message: 'Please input a URL.' },
                        { type: 'url', message: 'Please enter a valid URL.' },
                        { validator: serverValidateLongUrl },
                    ]}>
                    <Input placeholder="Long URL" prefix={<LinkOutlined className="site-from-item-icon" />} />
                </Form.Item>

                <Form.Item label="Expiration time" name='expiration_time'>
                    <DatePicker
                        format="YYYY-MM-DD HH:mm:ss"
                        disabledDate={current => current && current < moment().startOf('day')}
                        showTime={{ defaultValue: moment(props.linkInfo.expiration_time) }} />
                </Form.Item>

                <Form.List name="aliases">
                    {(fields, { add, remove }) => (
                        <div className='fix-alias-remove-button'>
                            {fields.map((field, index) => (
                                <Space key={field.key} style={{ display: 'flex', marginBottom: 8 }} align='start'>
                                    <Form.Item
                                        label={index === 0 ? 'Alias' : ''}
                                        name={[field.name, 'alias']}
                                        fieldKey={field.fieldKey}
                                        rules={[
                                            { required: true, message: 'Please enter an alias.' },
                                            { min: 5, message: 'Alias may be no shorter than 5 characters.' },
                                            { max: 60, message: 'Alias may be no longer than 60 characters.' },
                                            {
                                                pattern: /^[a-zA-Z0-9_.,-]*$/,
                                                message: 'Alias may consist only of numbers, letters, and the punctuation marks “.,-_”.'
                                            },
                                            { validator: serverValidateAlias },
                                        ]}>
                                        <Input disabled={!mayEditAliases} placeholder="Alias" />
                                    </Form.Item>

                                    <Form.Item
                                        label={index === 0 ? 'Description' : ''}
                                        name={[field.name, 'description']}
                                        fieldKey={field.fieldKey}>
                                        <Input disabled={!mayEditAliases} placeholder="Description" />
                                    </Form.Item>

                                    {!mayEditAliases ? <></> :
                                        <Button
                                            disabled={fields.length === 1}
                                            type="text"
                                            icon={<MinusCircleOutlined />}
                                            onClick={() => remove(field.name)} />}
                                </Space>
                            ))}

                            {!mayEditAliases ? <></> :
                                <Form.Item>
                                    <Button
                                        type="dashed"
                                        onClick={() => { add(); }}
                                        block>
                                        <PlusOutlined /> Add an alias
                                        </Button>
                                </Form.Item>}
                        </div>
                    )}
                </Form.List>
            </Form>

        </Modal>
    )
};